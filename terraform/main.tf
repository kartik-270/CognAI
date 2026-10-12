terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Example placeholder: Setting up a basic VPC for self-hosting the CognAI stack
resource "aws_vpc" "cognai_vpc" {
  cidr_block = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "cognai-vpc"
    Environment = var.environment
  }
}

resource "aws_subnet" "cognai_public_subnet" {
  vpc_id                  = aws_vpc.cognai_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name        = "cognai-public-subnet"
    Environment = var.environment
  }
}
