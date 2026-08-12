# Data Engineer Tech Challenge

This test is split into 3 sections:

1. **Data Pipelines**
2. **Databases**
3. **System Design**

## Section 1: Data Pipelines

An e-commerce company requires that users sign up for a membership on the website in order to purchase a product from the platform. As a data engineer under this company, you are tasked with designing and implementing a pipeline to process the membership applications submitted by users on an hourly interval.

Applications are batched into a varying number of datasets and dropped into a folder on an hourly basis. You are required to set up a pipeline to ingest, clean, perform validity checks, and create membership IDs for successful applications. An application is successful if:

Application mobile number is 8 digits
Applicant is over 18 years old as of 1 Jan 2022
Applicant has a valid email (email ends with @emailprovider.com or @emailprovider.net)
You are required to format datasets in the following manner:

Split name into first_name and last_name
Format birthday field into YYYYMMDD
Remove any rows which do not have a name field (treat this as unsuccessful applications)
Create a new field named above_18 based on the applicant's birthday
Membership IDs for successful applications should be the user's last name, followed by a SHA256 hash of the applicant's birthday, truncated to first 5 digits of hash (i.e <last_name>_<hash(YYYYMMDD)>)
You are required to consolidate these datasets and output the successful applications into a folder, which will be picked up by downstream engineers. Unsuccessful applications should be consolidated and dropped into a separate folder.

You can use common scheduling solutions such as cron or airflow to implement the scheduling component. Please provide a markdown file as documentation.

**Note: Please submit the processed dataset and scripts used**

---

## Section 2: Databases

You are appointed by the above e-commerce company to create a database infrastructure for their sales transactions. Purchases are being made by members of the e-commerce company on their website (you may use the first 50 members of a processed dataset from Section 1). Members can make multiple purchases. 

The following are known for each item listed for sale on the e-commerce website:
- Item Name
- Manufacturer Name
- Cost
- Weight (in kg)

Each transaction made by a member contains the following information:
- Membership ID
- Items bought (could be one item or multiple items)
- Total items price
- Total items weight

Set up a PostgreSQL database using the Docker [image](https://hub.docker.com/_/postgres) provided. We expect at least a Dockerfile which will stand up your database with the DDL statements to create the necessary tables. You are required to produce  entity-relationship diagrams as necessary to illustrate your design. 

Analysts from the e-commerce company will need to query some information from the database. Below are 2 of the sample queries from the analysts. Do note to design your database to account for a wide range of business use cases and queries. 
You are tasked to write a SQL statement for each of the following task:
1. Which are the top 10 members by spending
2. Which are the top 3 items that are frequently bought by members

---

## Section 3: System Design

You are designing data infrastructure on the cloud for a company whose main business is in processing images.

The company has a web application which allows users to upload images to the cloud using an API. There is also a separate web application which hosts a Kafka stream that uploads images to the same cloud environment. This Kafka stream has to be managed by the company's engineers.

Code has already been written by the company's software engineers to process the images. This code has to be hosted on the cloud. For archival purposes, the images and its metadata has to be stored in the cloud environment for 7 days, after which it has to be purged from the environment for compliance and privacy. The cloud environment should also host a Business Intelligence resource where the company's analysts can access and perform analytical computation on the data stored.

As a data engineer within the company, you are required to produce a system architecture diagram (Visio, PowerPoint, draw.io) depicting the end-to-end flow of the aforementioned pipeline. You may use any of the cloud providers (e.g. AWS, Azure, GCP) to host the environment. The architecture should specifically address the requirements/concerns above.

Do indicate any assumptions you have made regarding the architecture. You are required to provide a detailed explanation on the diagram.