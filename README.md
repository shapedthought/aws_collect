# AWS Collect

🤖 **AI Disclosure**      
Portions of the code and/or documentation for this project were created with the assistance of an AI system. All AI-generated content has been reviewed, tested, and validated by a human before inclusion in this repository. However, as the code is provided under the MIT license, please exercise due diligence when running the code.

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
- **Provides powerful CLI options** to filter regions and exclude resource types
- **Displays a resource summary at the end for quick review**
- **Handles API pagination to ensure all resources in large accounts are discovered**
- **Provided under the [MIT License](#license)** - **NO WARRANTY**

## Installation

1.  **Install dependencies**
    ```bash
    pip install boto3 click
    ```

2.  **Configure your AWS credentials**
    - Using the AWS CLI: `aws configure`
    - With environment variables: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
    - Using IAM roles if running on AWS EC2

## Usage

The script is now a command-line interface (CLI) tool. Save it as `aws_collect.py` and run it from your terminal.

#### **1. Get Help**

To see all available commands and options, use the `--help` flag.

```bash
python aws_collect.py --help
```

#### **2. Basic Scan**

Run the script with no options to scan all accessible AWS regions and save the results to a timestamped JSON file (e.g., `aws_resource_hierarchy_20250815_104600.json`).

```bash
python aws_collect.py
```

#### **3. Advanced Options**

You can combine the following flags to customize the scan:

| Option               | Short | Description                                                                         |
| -------------------- | ----- | ----------------------------------------------------------------------------------- |
| `--region`           | `-r`  | Specify a region to scan. Use this option multiple times for multiple regions.      |
| `--exclude`          | `-x`  | Exclude a resource type from the scan. Use multiple times to exclude more types.    |
| `--output`           | `-o`  | Set a custom filename for the output JSON file.                                     |
| `--verbose`          | `-v`  | Enable verbose debug logging, which is useful for troubleshooting.                  |

#### **Examples**

- **Scan specific regions:**
  ```bash
  python aws_collect.py --region us-east-1 --region eu-west-1
  ```

- **Scan all regions but exclude RDS and EFS resources:**
  ```bash
  python aws_collect.py --exclude rds --exclude efs
  ```

- **Scan a single region, exclude DynamoDB, and save to a custom file:**
  ```bash
  python aws_collect.py -r us-west-2 -x dynamodb -o my_compute_resources.json
  ```

- **Run a scan with verbose logging for debugging:**
  ```bash
  python aws_collect.py -v -r us-east-1
  ```

#### **4. Review the Output File**

The output file contains your resource hierarchy in a top-down fashion for all discovered resources, matching the logical arrangement shown in the architecture diagram above.

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

- **No data or permission errors**: Ensure your AWS IAM user/role has sufficient read-only permissions (e.g., policies with `Describe*`, `List*`, `Get*`) for EC2, EBS, VPC, RDS, DynamoDB, EFS, FSx, and Redshift resources.
- **API throttling**: The script uses Boto3 paginators to correctly handle large numbers of resources and is suitable for larger environments. In extremely large accounts with very high resource counts, you may still encounter AWS API rate limiting. If this occurs, consider running the scan for one region at a time.
