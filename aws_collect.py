import boto3
from botocore.exceptions import ClientError
from collections import defaultdict
import json
import logging
from datetime import datetime

# --- Setup Logging ---
# Configure logging to provide informative output.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AWSResourceHierarchy:
    def __init__(self):
        """
        Initializes the data structure for holding the resource hierarchy.
        Using nested defaultdicts simplifies adding new regions and VPCs.
        """
        self.hierarchy = defaultdict(lambda: defaultdict(dict))

    def build_hierarchy(self, regions=None):
        """
        Builds a complete AWS resource hierarchy.
        If regions are not specified, it attempts to discover all available regions.
        """
        if not regions:
            try:
                ec2_client = boto3.client('ec2')
                regions = [r['RegionName'] for r in ec2_client.describe_regions()['Regions']]
            except ClientError as e:
                logging.error(f"Error getting AWS regions. Check credentials and permissions. Details: {e}")
                return {}
        
        for region in regions:
            logging.info(f"Processing region: {region}")
            self._build_region_hierarchy(region)
            
        return dict(self.hierarchy)
    
    def _build_region_hierarchy(self, region):
        """Builds the hierarchy for a single specified region."""
        try:
            # Initialize clients for the specified region
            ec2 = boto3.client('ec2', region_name=region)
            rds = boto3.client('rds', region_name=region)
            efs = boto3.client('efs', region_name=region)
            fsx = boto3.client('fsx', region_name=region)
            dynamodb = boto3.client('dynamodb', region_name=region)
            redshift = boto3.client('redshift', region_name=region)
            
            # Step 1: Get all VPCs in the region
            vpcs = self._get_vpcs(ec2)
            if not vpcs:
                logging.warning(f"No VPCs found or accessible in region {region}.")
            
            # Pre-fetch DB subnet groups to map Subnet Group Name to VpcId
            db_subnet_groups = self._get_db_subnet_groups(rds)
            
            for vpc in vpcs:
                vpc_id = vpc['VpcId']
                
                # Step 2: Build the hierarchy for each VPC
                self.hierarchy[region][vpc_id] = {
                    'vpc_info': vpc,
                    'network_components': self._get_network_components(ec2, vpc_id),
                    'security_groups': self._get_security_groups(ec2, vpc_id),
                    'resources': {
                        'ec2_instances': self._get_ec2_with_ebs(ec2, vpc_id),
                        'rds_instances': self._get_rds_resources(rds, vpc_id, db_subnet_groups),
                        'efs_filesystems': self._get_efs_resources(efs, vpc_id),
                        'fsx_filesystems': self._get_fsx_resources(fsx, vpc_id),
                        'redshift_clusters': self._get_redshift_resources(redshift, vpc_id)
                    }
                }
            
            # Step 3: Handle resources that are region-wide (not tied to a VPC)
            self.hierarchy[region]['region_wide'] = {
                'dynamodb_tables': self._get_dynamodb_tables(dynamodb)
            }
            
        except ClientError as e:
            logging.error(f"Error processing region {region}. It might be disabled or you lack permissions. Details: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred in region {region}: {e}")

    def _get_paginated_results(self, client, method, key, filters=None):
        """Generic helper function to handle pagination for Boto3 clients."""
        try:
            paginator = client.get_paginator(method)
            page_iterator = paginator.paginate(**(filters or {}))
            
            results = []
            for page in page_iterator:
                results.extend(page.get(key, []))
            return results
        except ClientError as e:
            logging.error(f"Error during pagination for {client.meta.service_model.service_name}/{method}: {e}")
            return []

    def _get_vpcs(self, ec2):
        """Get all VPCs in a region using pagination."""
        return self._get_paginated_results(ec2, 'describe_vpcs', 'Vpcs')
    
    def _get_network_components(self, ec2, vpc_id):
        """Get all network components for a specific VPC using pagination."""
        vpc_filter = {'Filters': [{'Name': 'vpc-id', 'Values': [vpc_id]}]}
        igw_filter = {'Filters': [{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]}
        
        components = {}
        components['subnets'] = self._get_paginated_results(ec2, 'describe_subnets', 'Subnets', vpc_filter)
        components['route_tables'] = self._get_paginated_results(ec2, 'describe_route_tables', 'RouteTables', vpc_filter)
        components['internet_gateways'] = self._get_paginated_results(ec2, 'describe_internet_gateways', 'InternetGateways', igw_filter)
        components['nat_gateways'] = self._get_paginated_results(ec2, 'describe_nat_gateways', 'NatGateways', vpc_filter)
        return components
    
    def _get_security_groups(self, ec2, vpc_id):
        """Get all security groups for a specific VPC using pagination."""
        vpc_filter = {'Filters': [{'Name': 'vpc-id', 'Values': [vpc_id]}]}
        return self._get_paginated_results(ec2, 'describe_security_groups', 'SecurityGroups', vpc_filter)

    def _get_ec2_with_ebs(self, ec2, vpc_id):
        """Get EC2 instances with their associated EBS volumes using pagination."""
        instances_with_ebs = []
        vpc_filter = {'Filters': [{'Name': 'vpc-id', 'Values': [vpc_id]}]}
        
        reservations = self._get_paginated_results(ec2, 'describe_instances', 'Reservations', vpc_filter)
        
        for reservation in reservations:
            for instance in reservation.get('Instances', []):
                ebs_volumes = []
                for bd in instance.get('BlockDeviceMappings', []):
                    ebs = bd.get('Ebs')
                    if ebs and 'VolumeId' in ebs:
                        volume_details = self._get_volume_details(ec2, ebs['VolumeId'])
                        ebs_volumes.append({
                            'volume_id': ebs['VolumeId'],
                            'device_name': bd.get('DeviceName'),
                            'delete_on_termination': ebs.get('DeleteOnTermination', False),
                            'volume_details': volume_details
                        })
                
                instances_with_ebs.append({
                    'instance_id': instance.get('InstanceId'),
                    'instance_type': instance.get('InstanceType'),
                    'state': instance.get('State', {}).get('Name'),
                    'subnet_id': instance.get('SubnetId'),
                    'security_groups': instance.get('SecurityGroups', []),
                    'tags': instance.get('Tags', []),
                    'ebs_volumes': ebs_volumes
                })
        return instances_with_ebs
    
    def _get_volume_details(self, ec2, volume_id):
        """Get detailed information for a single EBS volume."""
        try:
            response = ec2.describe_volumes(VolumeIds=[volume_id])
            if not response.get('Volumes'):
                return {}
            volume = response['Volumes'][0]
            return {
                'size': volume.get('Size'),
                'volume_type': volume.get('VolumeType'),
                'iops': volume.get('Iops'),
                'encrypted': volume.get('Encrypted', False),
                'state': volume.get('State')
            }
        except ClientError as e:
            logging.error(f"Error getting details for volume {volume_id}: {e}")
            return {}

    def _get_db_subnet_groups(self, rds):
        """Fetch all DB subnet groups and map their names to VPC IDs for efficient lookup."""
        subnet_groups = self._get_paginated_results(rds, 'describe_db_subnet_groups', 'DBSubnetGroups')
        return {sg['DBSubnetGroupName']: sg['VpcId'] for sg in subnet_groups}

    def _get_rds_resources(self, rds, vpc_id, db_subnet_groups):
        """Get RDS instances and Aurora clusters for a given VPC."""
        rds_resources = {'db_instances': [], 'clusters': []}
        
        # RDS DB Instances must be filtered in code as the API doesn't support a VPC filter.
        db_instances = self._get_paginated_results(rds, 'describe_db_instances', 'DBInstances')
        for db in db_instances:
            subnet_group_name = db.get('DBSubnetGroup', {}).get('DBSubnetGroupName')
            if db_subnet_groups.get(subnet_group_name) == vpc_id:
                rds_resources['db_instances'].append({
                    'db_instance_id': db.get('DBInstanceIdentifier'),
                    'engine': db.get('Engine'),
                    'instance_class': db.get('DBInstanceClass'),
                    'multi_az': db.get('MultiAZ', False)
                })
        
        # RDS DB Clusters must also be filtered in code.
        clusters = self._get_paginated_results(rds, 'describe_db_clusters', 'DBClusters')
        for cluster in clusters:
            subnet_group_name = cluster.get('DBSubnetGroup')
            if db_subnet_groups.get(subnet_group_name) == vpc_id:
                rds_resources['clusters'].append({
                    'cluster_id': cluster.get('DBClusterIdentifier'),
                    'engine': cluster.get('Engine'),
                    'cluster_members': [member.get('DBInstanceIdentifier') for member in cluster.get('DBClusterMembers', [])]
                })
        return rds_resources

    def _get_efs_resources(self, efs, vpc_id):
        """Get EFS file systems for a VPC. Requires checking mount targets."""
        efs_systems = []
        filesystems = self._get_paginated_results(efs, 'describe_file_systems', 'FileSystems')
        for fs in filesystems:
            fs_id = fs.get('FileSystemId')
            try:
                mount_targets = efs.describe_mount_targets(FileSystemId=fs_id)['MountTargets']
                for mt in mount_targets:
                    if mt.get('VpcId') == vpc_id:
                        efs_systems.append({
                            'file_system_id': fs_id,
                            'life_cycle_state': fs.get('LifeCycleState'),
                            'performance_mode': fs.get('PerformanceMode'),
                            'encrypted': fs.get('Encrypted', False)
                        })
                        break # Found a mount target in the correct VPC, no need to check others for this FS
            except ClientError as e:
                logging.warning(f"Could not describe mount targets for EFS {fs_id}: {e}")
        return efs_systems

    def _get_fsx_resources(self, fsx, vpc_id):
        """Get FSx file systems for a VPC."""
        fsx_systems = []
        # FSx describe_file_systems must be filtered in code.
        filesystems = self._get_paginated_results(fsx, 'describe_file_systems', 'FileSystems')
        for fs in filesystems:
            if fs.get('VpcId') == vpc_id:
                fsx_systems.append({
                    'file_system_id': fs.get('FileSystemId'),
                    'file_system_type': fs.get('FileSystemType'),
                    'lifecycle_state': fs.get('Lifecycle'),
                    'storage_capacity': fs.get('StorageCapacity'),
                    'subnet_ids': fs.get('SubnetIds', [])
                })
        return fsx_systems

    def _get_redshift_resources(self, redshift, vpc_id):
        """Get Redshift clusters for a VPC."""
        redshift_resources = {'clusters': []}
        # Redshift describe_clusters must be filtered in code.
        clusters = self._get_paginated_results(redshift, 'describe_clusters', 'Clusters')
        for cluster in clusters:
            if cluster.get('VpcId') == vpc_id:
                redshift_resources['clusters'].append({
                    'cluster_identifier': cluster.get('ClusterIdentifier'),
                    'node_type': cluster.get('NodeType'),
                    'number_of_nodes': cluster.get('NumberOfNodes'),
                    'cluster_status': cluster.get('ClusterStatus')
                })
        return redshift_resources
    
    def _get_dynamodb_tables(self, dynamodb):
        """Get all DynamoDB tables in a region (region-wide resource)."""
        tables = []
        table_names = self._get_paginated_results(dynamodb, 'list_tables', 'TableNames')
        for table_name in table_names:
            try:
                table_details = dynamodb.describe_table(TableName=table_name)['Table']
                tables.append({
                    'table_name': table_name,
                    'table_status': table_details.get('TableStatus'),
                    'item_count': table_details.get('ItemCount', 0),
                    'billing_mode': table_details.get('BillingModeSummary', {}).get('BillingMode', 'PROVISIONED')
                })
            except ClientError as e:
                logging.error(f"Error describing DynamoDB table {table_name}: {e}")
        return tables

    def save_to_file(self, hierarchy, filename=None):
        """Saves the final hierarchy to a JSON file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"aws_resource_hierarchy_{timestamp}.json"
            
        try:
            with open(filename, 'w') as f:
                json.dump(hierarchy, f, indent=2, default=str)
            logging.info(f"Hierarchy successfully saved to {filename}")
        except Exception as e:
            logging.error(f"Error saving hierarchy to file: {e}")

    def print_summary(self, hierarchy):
        """Prints a high-level summary of the discovered resources."""
        summary = "\n" + "="*50 + "\nAWS RESOURCE HIERARCHY SUMMARY\n" + "="*50
        
        for region, vpcs in hierarchy.items():
            summary += f"\nRegion: {region}\n"
            
            for vpc_id, vpc_data in vpcs.items():
                if vpc_id == 'region_wide':
                    dynamodb_count = len(vpc_data.get('dynamodb_tables', []))
                    if dynamodb_count > 0:
                        summary += f"  Region-wide Resources:\n"
                        summary += f"    DynamoDB Tables: {dynamodb_count}\n"
                else:
                    summary += f"  VPC: {vpc_id}\n"
                    network = vpc_data.get('network_components', {})
                    summary += f"    Subnets: {len(network.get('subnets', []))}\n"
                    summary += f"    Security Groups: {len(vpc_data.get('security_groups', []))}\n"
                    
                    resources = vpc_data.get('resources', {})
                    ec2_instances = resources.get('ec2_instances', [])
                    total_ebs = sum(len(i.get('ebs_volumes', [])) for i in ec2_instances)
                    
                    summary += f"    EC2 Instances: {len(ec2_instances)}\n"
                    summary += f"    EBS Volumes: {total_ebs}\n"
                    summary += f"    RDS Instances: {len(resources.get('rds_instances', {}).get('db_instances', []))}\n"
                    summary += f"    RDS Clusters: {len(resources.get('rds_instances', {}).get('clusters', []))}\n"
                    summary += f"    EFS File Systems: {len(resources.get('efs_filesystems', []))}\n"
                    summary += f"    FSx File Systems: {len(resources.get('fsx_filesystems', []))}\n"
                    summary += f"    Redshift Clusters: {len(resources.get('redshift_clusters', {}).get('clusters', []))}\n"
        
        logging.info(summary)

def main():
    """Main execution function to run the hierarchy builder."""
    logging.info("Starting AWS Resource Hierarchy Builder")
    
    builder = AWSResourceHierarchy()
    
    # Set to None to scan all available regions.
    # Or specify a list: regions = ['us-east-1', 'us-west-2']
    regions = None
    
    try:
        logging.info("Building AWS resource hierarchy...")
        hierarchy = builder.build_hierarchy(regions)
        
        if not hierarchy:
            logging.warning("No resources found or access was denied. Check your AWS credentials and IAM permissions.")
            return
        
        builder.print_summary(hierarchy)
        builder.save_to_file(hierarchy)
        
        logging.info("Hierarchy building completed successfully!")
        
    except Exception as e:
        logging.critical(f"A critical error occurred during execution: {e}", exc_info=True)
        logging.critical("Ensure you have valid AWS credentials configured (e.g., via environment variables, IAM role).")

if __name__ == "__main__":
    main()
