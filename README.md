# Overview

Technical Assessment for stealth company.

## Challenges

I come from a Terraform world, and have never used Pulumi until this project. There was a (very) steep learning curve to figure out how Pulumi interacts with AWS. This isn't the most elegant solution, but it does meet the following criteria:

* This infrastructure is a production quality infrastructure
* *The final goal is to run both services (Web and API) on AWS. We are leaving all the details to you.
* Be mindful of security best practices. The API is not a public API, and it is only accessed by Web UI.
* Only the web UI should be accessible through the internet (port 80)
* Tag all the environment resources for auditing purposes

If you encounter things that aren't done in the "Pulumi" way, it's due to my newness to the tool.

## Improvements

Things that given more time, and a better understanding of Pulumi, that I'd improve:

* Add Cloudwatch everywhere
* Bake in prometheus so we can get some real-time metrics going
* Rework the Docker containers to operate on different ports... just changing the launchSettings.json did not do anything, and it became time prohibitive to figure this out. Fixing that would prevent the need for seperate frontend/backend fargate clusters