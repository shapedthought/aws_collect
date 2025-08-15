# AWS Collect

🤖 **AI Disclosure**      
Portions of the code and/or documentation for this project were created with the assistance of an AI system. All AI-generated content has been reviewed, tested, and validated by a human before inclusion in this repository. However, as the code is provided under the MIT license, please exercise due diligence when running the code.

## Overview

The **AWS Collect** script programmatically collects and organizes your AWS resources in a top-down, hierarchical structure, as depicted in the supplied architecture diagram:

```
Account
│
├── global_resources
│   └── s3_buckets
│
└── Region
    │
    ├── VPC
    │   │
    │   ├── vpc_info
    │   ├── network_components
    │   │     ├── subnets, route_tables, etc.
    │   ├── security_groups
    │   └── resources
    │         ├── ec2_instances (& ebs_volumes)
    │         ├── rds_instances
    │         ├── efs_filesystems
    │         ├── fsx_filesystems
    │         └── redshift_clusters
    │
    └── region_wide
          └── dynamodb_tables
```

The script is designed to support all resource types relevant to Veeam Backup for AWS, making it ideal for inventory, migration planning, and backup sizing scenarios.

- **Discovers and groups AWS resources by scope**:
  - **Global**: S3 Buckets
  - **Regional**: VPCs, DynamoDB Tables
  - **VPC-Specific**: EC2, RDS, Aurora, EFS, FSx, Redshift

- **Includes key capacity metrics for all supported resources**:
  - S3: Bucket size and object count
  - EBS: Volume size
  - RDS: Allocated storage
  - EFS/FSx/DynamoDB: Storage size and/or item counts

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

## 🔒 Security Best Practices

It is **strongly recommended** to run this script using AWS credentials that adhere to the **principle of least privilege**. Since the tool only needs to discover and read resource configurations, you should use an IAM user or role with **read-only permissions**.

#### **Using the `ReadOnlyAccess` AWS Managed Policy**

The easiest way to achieve this is to create an IAM user or role and attach the AWS managed policy named `ReadOnlyAccess`. This policy grants the necessary `Describe*`, `List*`, and `Get*` permissions for all AWS services without allowing any modifications.

#### **Creating a Custom Policy (Advanced)**

For even tighter security, you can create a custom IAM policy that only includes the specific permissions required by this script. This would limit access to only the services being scanned (EC2, VPC, S3, RDS, etc.) instead of all AWS services.

**Never run this script with an administrator or power-user account in a production environment.**

## Usage

The script is a command-line interface (CLI) tool. Save it as `aws_collect.py` and run it from your terminal.

#### **1. Get Help**

To see all available commands and options, use the `--help` flag.

```bash
python aws_collect.py --help
```

#### **2. Basic Scan**

Run the script with no options to scan all global and regional resources, saving the results to a timestamped JSON file (e.g., `aws_resource_hierarchy_20250815_104600.json`).

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

- **Scan all resources but exclude S3 and RDS:**
  ```bash
  python aws_collect.py --exclude s3 --exclude rds
  ```

- **Scan a single region, exclude DynamoDB, and save to a custom file:**
  ```bash
  python aws_collect.py -r us-west-2 -x dynamodb -o my_compute_resources.json
  ```

- **Scan only global S3 resources (by excluding everything else):**
  ```bash
  python aws_collect.py --exclude ec2 --exclude rds --exclude efs --exclude fsx --exclude redshift --exclude dynamodb
  ```

#### **4. Review the Output File**

The output file contains your resource hierarchy in a top-down fashion.

Example (JSON snippet):
```json
{
  "global_resources": {
    "s3_buckets": [
      {
        "name": "my-production-bucket",
        "creation_date": "2024-01-01T12:00:00+00:00",
        "region": "eu-west-1",
        "size_bytes": 10737418240,
        "object_count": 5201
      }
    ]
  },
  "us-east-1": {
    "vpc-xxxxxxx": {
      "vpc_info": { ... },
      "resources": {
        "ec2_instances": [ ... ],
        "rds_instances": {
           "db_instances": [
              {
                 "db_instance_id": "my-db",
                 "allocated_storage": 100
              }
           ]
        }
      }
    }
  }
}
```

## Extensibility

The script is modular—extend it to add new resource types or customize the hierarchy as needed for your organization.

## Troubleshooting

- **No data or permission errors**: Ensure your IAM user/role has sufficient read-only permissions (e.g., policies with `Describe*`, `List*`, `Get*`) for all target services. Note that S3 discovery also requires `cloudwatch:GetMetricStatistics`.
- **Inaccurate S3 metrics**: S3 bucket size and object count are retrieved from CloudWatch, which updates these metrics approximately once per day. The reported figures will reflect the last daily update.
- **API throttling**: The script uses B3 paginators to handle large numbers of resources. In extremely large accounts, you may still encounter AWS API rate limiting. If this occurs, consider running the scan for one region at a time.
