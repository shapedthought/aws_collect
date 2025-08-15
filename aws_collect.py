import boto3
from collections import defaultdict
import json
from datetime import datetime

class AWSResourceHierarchy:
    def __init__(self):
        # If you want nested defaultdicts:
        self.hierarchy = defaultdict(lambda: defaultdict(dict))

        # Or, if you want to avoid type issues, use a plain dict:
        # self.hierarchy = {}
        
    def build_hierarchy(self, regions=None):
        """Build complete AWS resource hierarchy by region"""
        if not regions:
            try:
                ec2 = boto3.client('ec2')
                regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
            except Exception as e:
                print(f"Error getting regions: {e}")
                return {}
        
        for region in regions:
            print(f"Processing region: {region}")
            self._build_region_hierarchy(region)
            
        return dict(self.hierarchy)
    
    def _build_region_hierarchy(self, region):
        """Build hierarchy for a specific region"""
        try:
            # Initialize clients for the region
            ec2 = boto3.client('ec2', region_name=region)
            rds = boto3.client('rds', region_name=region)
            efs = boto3.client('efs', region_name=region)
            fsx = boto3.client('fsx', region_name=region)
            dynamodb = boto3.client('dynamodb', region_name=region)
            redshift = boto3.client('redshift', region_name=region)
            
            # Step 1: Get all VPCs in region
            vpcs = self._get_vpcs(ec2)
            
            for vpc in vpcs:
                vpc_id = vpc['VpcId']
                
                # Step 2: Build VPC-level hierarchy
                self.hierarchy[region][vpc_id] = {
                    'vpc_info': vpc,
                    'network_components': self._get_network_components(ec2, vpc_id),
                    'security_groups': self._get_security_groups(ec2, vpc_id),
                    'resources': {
                        'ec2_instances': self._get_ec2_with_ebs(ec2, vpc_id),
                        'rds_instances': self._get_rds_resources(rds, vpc_id),
                        'efs_filesystems': self._get_efs_resources(efs, vpc_id),
                        'fsx_filesystems': self._get_fsx_resources(fsx, vpc_id),
                        'redshift_clusters': self._get_redshift_resources(redshift, vpc_id)
                    }
                }
            
            # Step 3: Handle region-wide resources (DynamoDB, etc.)
            self.hierarchy[region]['region_wide'] = {
                'dynamodb_tables': self._get_dynamodb_tables(dynamodb)
            }
            
        except Exception as e:
            print(f"Error processing region {region}: {e}")

    def _get_vpcs(self, ec2):
        """Get all VPCs in region"""
        try:
            response = ec2.describe_vpcs()
            return response['Vpcs']
        except Exception as e:
            print(f"Error getting VPCs: {e}")
            return []
    
    def _get_network_components(self, ec2, vpc_id):
        """Get network components for VPC"""
        components = {}
        
        try:
            # Subnets
            subnets = ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['Subnets']
            components['subnets'] = subnets
            
            # Route Tables
            route_tables = ec2.describe_route_tables(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['RouteTables']
            components['route_tables'] = route_tables
            
            # Internet Gateways
            igws = ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
            )['InternetGateways']
            components['internet_gateways'] = igws
            
            # NAT Gateways
            nat_gws = ec2.describe_nat_gateways(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['NatGateways']
            components['nat_gateways'] = nat_gws
            
        except Exception as e:
            print(f"Error getting network components for VPC {vpc_id}: {e}")
            
        return components
    
    def _get_security_groups(self, ec2, vpc_id):
        """Get security groups for VPC"""
        try:
            response = ec2.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            return response['SecurityGroups']
        except Exception as e:
            print(f"Error getting security groups for VPC {vpc_id}: {e}")
            return []

    def _get_ec2_with_ebs(self, ec2, vpc_id):
        """Get EC2 instances with associated EBS volumes"""
        instances_with_ebs = []
        
        try:
            response = ec2.describe_instances(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    # Get EBS volumes attached to this instance
                    ebs_volumes = []
                    for bd in instance.get('BlockDeviceMappings', []):
                        ebs = bd.get('Ebs')
                        if ebs:
                            # Get detailed volume information
                            volume_details = self._get_volume_details(ec2, ebs['VolumeId'])
                            ebs_volumes.append({
                                'volume_id': ebs['VolumeId'],
                                'device_name': bd['DeviceName'],
                                'delete_on_termination': ebs.get('DeleteOnTermination', False),
                                'volume_details': volume_details
                            })
                    
                    instances_with_ebs.append({
                        'instance_id': instance['InstanceId'],
                        'instance_type': instance['InstanceType'],
                        'state': instance['State']['Name'],
                        'subnet_id': instance.get('SubnetId'),
                        'security_groups': instance.get('SecurityGroups', []),
                        'tags': instance.get('Tags', []),
                        'ebs_volumes': ebs_volumes
                    })
                    
        except Exception as e:
            print(f"Error getting EC2 instances for VPC {vpc_id}: {e}")
            
        return instances_with_ebs
    
    def _get_volume_details(self, ec2, volume_id):
        """Get detailed EBS volume information"""
        try:
            response = ec2.describe_volumes(VolumeIds=[volume_id])
            volume = response['Volumes'][0]
            return {
                'size': volume['Size'],
                'volume_type': volume['VolumeType'],
                'iops': volume.get('Iops'),
                'encrypted': volume.get('Encrypted', False),
                'state': volume['State']
            }
        except Exception as e:
            print(f"Error getting volume details for {volume_id}: {e}")
            return {}

    def _get_rds_resources(self, rds, vpc_id):
        """Get RDS instances and Aurora clusters"""
        rds_resources = {'db_instances': [], 'clusters': []}
        
        try:
            # DB Instances
            db_instances = rds.describe_db_instances()['DBInstances']
            for db in db_instances:
                if db.get('DBSubnetGroup', {}).get('VpcId') == vpc_id:
                    rds_resources['db_instances'].append({
                        'db_instance_id': db['DBInstanceIdentifier'],
                        'engine': db['Engine'],
                        'instance_class': db['DBInstanceClass'],
                        'allocated_storage': db.get('AllocatedStorage'),
                        'multi_az': db.get('MultiAZ', False),
                        'vpc_security_groups': db.get('VpcSecurityGroups', [])
                    })
            
            # Aurora Clusters
            clusters = rds.describe_db_clusters()['DBClusters']
            for cluster in clusters:
                if cluster.get('DBSubnetGroup', {}).get('VpcId') == vpc_id:
                    rds_resources['clusters'].append({
                        'cluster_id': cluster['DBClusterIdentifier'],
                        'engine': cluster['Engine'],
                        'cluster_members': cluster.get('DBClusterMembers', []),
                        'vpc_security_groups': cluster.get('VpcSecurityGroups', [])
                    })
                    
        except Exception as e:
            print(f"Error getting RDS resources: {e}")
            
        return rds_resources

    def _get_efs_resources(self, efs, vpc_id):
        """Get EFS file systems"""
        efs_systems = []
        try:
            filesystems = efs.describe_file_systems()['FileSystems']
            for fs in filesystems:
                # Get mount targets to check VPC
                mount_targets = efs.describe_mount_targets(FileSystemId=fs['FileSystemId'])['MountTargets']
                for mt in mount_targets:
                    if mt.get('VpcId') == vpc_id:
                        efs_systems.append({
                            'file_system_id': fs['FileSystemId'],
                            'creation_token': fs['CreationToken'],
                            'life_cycle_state': fs['LifeCycleState'],
                            'size_in_bytes': fs.get('SizeInBytes', {}).get('Value', 0),
                            'performance_mode': fs.get('PerformanceMode'),
                            'encrypted': fs.get('Encrypted', False)
                        })
                        break
        except Exception as e:
            print(f"Error getting EFS resources: {e}")
            
        return efs_systems

    def _get_fsx_resources(self, fsx, vpc_id):
        """Get FSx file systems"""
        fsx_systems = []
        try:
            filesystems = fsx.describe_file_systems()['FileSystems']
            for fs in filesystems:
                if fs.get('VpcId') == vpc_id:
                    fsx_systems.append({
                        'file_system_id': fs['FileSystemId'],
                        'file_system_type': fs['FileSystemType'],
                        'lifecycle_state': fs['Lifecycle'],
                        'storage_capacity': fs.get('StorageCapacity'),
                        'vpc_id': fs.get('VpcId'),
                        'subnet_ids': fs.get('SubnetIds', [])
                    })
        except Exception as e:
            print(f"Error getting FSx resources: {e}")
            
        return fsx_systems

    def _get_redshift_resources(self, redshift, vpc_id):
        """Get Redshift clusters"""
        redshift_resources = {'clusters': [], 'serverless_namespaces': []}
        
        try:
            # Redshift Clusters
            clusters = redshift.describe_clusters()['Clusters']
            for cluster in clusters:
                if cluster.get('VpcId') == vpc_id:
                    redshift_resources['clusters'].append({
                        'cluster_identifier': cluster['ClusterIdentifier'],
                        'node_type': cluster.get('NodeType'),
                        'number_of_nodes': cluster.get('NumberOfNodes'),
                        'cluster_status': cluster.get('ClusterStatus'),
                        'vpc_id': cluster.get('VpcId'),
                        'vpc_security_groups': cluster.get('VpcSecurityGroups', [])
                    })
                    
        except Exception as e:
            print(f"Error getting Redshift resources: {e}")
            
        return redshift_resources
    
    def _get_dynamodb_tables(self, dynamodb):
        """Get DynamoDB tables (region-wide resource)"""
        tables = []
        try:
            table_names = dynamodb.list_tables()['TableNames']
            for table_name in table_names:
                table_details = dynamodb.describe_table(TableName=table_name)['Table']
                tables.append({
                    'table_name': table_name,
                    'table_status': table_details['TableStatus'],
                    'item_count': table_details.get('ItemCount', 0),
                    'table_size_bytes': table_details.get('TableSizeBytes', 0),
                    'billing_mode': table_details.get('BillingModeSummary', {}).get('BillingMode', 'PROVISIONED')
                })
        except Exception as e:
            print(f"Error getting DynamoDB tables: {e}")
            
        return tables

    def save_to_file(self, hierarchy, filename=None):
        """Save hierarchy to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"aws_resource_hierarchy_{timestamp}.json"
            
        try:
            with open(filename, 'w') as f:
                json.dump(hierarchy, f, indent=2, default=str)
            print(f"Hierarchy saved to {filename}")
        except Exception as e:
            print(f"Error saving to file: {e}")

    def print_summary(self, hierarchy):
        """Print a summary of the hierarchy"""
        print("\n" + "="*50)
        print("AWS RESOURCE HIERARCHY SUMMARY")
        print("="*50)
        
        for region, vpcs in hierarchy.items():
            print(f"\nRegion: {region}")
            
            for vpc_id, vpc_data in vpcs.items():
                if vpc_id == 'region_wide':
                    dynamodb_count = len(vpc_data.get('dynamodb_tables', []))
                    if dynamodb_count > 0:
                        print(f"  Region-wide Resources:")
                        print(f"    DynamoDB Tables: {dynamodb_count}")
                else:
                    print(f"  VPC: {vpc_id}")
                    
                    # Network components
                    network = vpc_data.get('network_components', {})
                    print(f"    Subnets: {len(network.get('subnets', []))}")
                    print(f"    Security Groups: {len(vpc_data.get('security_groups', []))}")
                    
                    # Resources
                    resources = vpc_data.get('resources', {})
                    ec2_instances = resources.get('ec2_instances', [])
                    print(f"    EC2 Instances: {len(ec2_instances)}")
                    
                    # Count EBS volumes
                    total_ebs = sum(len(instance.get('ebs_volumes', [])) for instance in ec2_instances)
                    print(f"    EBS Volumes: {total_ebs}")
                    
                    print(f"    RDS Instances: {len(resources.get('rds_instances', {}).get('db_instances', []))}")
                    print(f"    RDS Clusters: {len(resources.get('rds_instances', {}).get('clusters', []))}")
                    print(f"    EFS File Systems: {len(resources.get('efs_filesystems', []))}")
                    print(f"    FSx File Systems: {len(resources.get('fsx_filesystems', []))}")
                    print(f"    Redshift Clusters: {len(resources.get('redshift_clusters', {}).get('clusters', []))}")

def main():
    """Main execution function"""
    print("AWS Resource Hierarchy Builder")
    print("Supports all Veeam Backup for AWS resource types")
    print("-" * 50)
    
    # Initialize the hierarchy builder
    builder = AWSResourceHierarchy()
    
    # You can specify specific regions or leave empty for all regions
    regions = None  # or ['us-east-1', 'us-west-2'] for specific regions
    
    try:
        # Build the hierarchy
        print("Building AWS resource hierarchy...")
        hierarchy = builder.build_hierarchy(regions)
        
        if not hierarchy:
            print("No resources found or access denied. Check your AWS credentials and permissions.")
            return
        
        # Print summary
        builder.print_summary(hierarchy)
        
        # Save to file
        builder.save_to_file(hierarchy)
        
        print(f"\nHierarchy building completed successfully!")
        
    except Exception as e:
        print(f"Error building hierarchy: {e}")
        print("Make sure you have valid AWS credentials configured.")

if __name__ == "__main__":
    main()
