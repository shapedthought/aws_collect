# AWS Collect

🤖 AI Disclosure
Portions of the code and/or documentation for this project were created with the assistance of an AI system.      

All AI-generated content has been reviewed, tested, and validated by a human before inclusion in this repository.

However, as the code is provided under MIT please excercise due dilience when running the code.


## Overview

The **AWS Collect** script programmatically collects and organizes your AWS resources in a top-down, hierarchical structure, as depicted in the supplied architecture diagram:

```
Region
│
├── VPC
│   │
│   ├── vpc_info
│   ├── network_components
│   │     ├── subnets
│   │     ├── route_tables
│   │     ├── internet_gateways
│   │     └── nat_gateways
│   ├── security_groups
│   └── resources
│         ├── ec2_instances
│         │     └── ebs_volumes
│         ├── rds_instances
│         │     ├── db_instances
│         │     └── clusters
│         ├── efs_filesystems
│         ├── fsx_filesystems
│         └── redshift_clusters
│
└── region_wide
      └── dynamodb_tables

```

The script is designed to support all resource types relevant to Veeam Backup for AWS, making it ideal for inventory, migration planning, and backup sizing scenarios.

- **Discovers and groups AWS resources by**:  
  - Region  
  - VPC  
  - Network components (Subnets, Route Tables, Gateways)  
  - Security Groups  
  - EC2 Instances with associated EBS volumes  
  - Other Veeam-supported resources: RDS, Aurora, DynamoDB, EFS, FSx, Redshift

- **Outputs everything as a single, structured JSON file**  
- **Displays a resource summary at the end for quick review**  
- **Handles errors gracefully and is easily extensible with new AWS resource types**  
- **Provided under the [MIT License](#license)** - **NO WARRENTY** 

## Installation

1. **Install dependencies**
    ```bash
    pip install boto3
    ```

2. **Configure your AWS credentials**  
   - Using the AWS CLI: `aws configure`  
   - With environment variables: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
   - Using IAM roles if running on AWS EC2

## Usage

1. **Save the script as** `aws_collect.py`
2. **Run the script**
    ```bash
    python aws_collect.py
    ```

   - The script will process all regions by default, or you can specify a list of regions to scan.
   - Progress and a summary are printed to the console.
   - Results are saved to a timestamped JSON file (e.g., `aws_resource_hierarchy_YYYYMMDD_HHMMSS.json`).

3. **Review the Output File**  
   The output file contains your resource hierarchy in top-down fashion for all discovered resources, matching the logical arrangement shown in the architecture diagram above.  
   Example (JSON snippet):
   ```json
   {
      "us-east-1": {
         "vpc-xxxxxxx": {
            "vpc_info": { ... },
            "network_components": { ... },
            "security_groups": [ ... ],
            "resources": {
               "ec2_instances": [
                  {
                     "instance_id": "i-abcdefg",
                     "ebs_volumes": [
                        { "volume_id": "vol-123456..." }
                     ]
                  }
               ],
               ...
            }
         },
         "region_wide": {
            "dynamodb_tables": [ ... ]
         }
      }
   }
   ```

## Extensibility

The script is modular—extend it to add new resource types or customize the hierarchy as needed for your organization.

## Troubleshooting

- **No data or permission errors**: Ensure your AWS IAM user/role has at least `Describe*` permissions for EC2, EBS, VPC, RDS, DynamoDB, EFS, FSx, and Redshift resources.
- **API throttling**: The script is designed for moderate AWS account sizes and no pagination handling. For larger environments, enhance the pagination logic.
