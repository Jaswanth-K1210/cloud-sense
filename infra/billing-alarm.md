# $10 billing alarm for the sandbox account

Set this up before seeding. Billing metrics only exist in **us-east-1**.

1. Sign in as the account root or an admin, open **Billing and Cost Management → Billing preferences**, and turn on
   **Receive CloudWatch billing alerts**. Save. (Metrics appear within a few hours.)
2. Create an SNS topic for the alert and subscribe your email:
   ```bash
   aws sns create-topic --name billing-alarm --region us-east-1
   aws sns subscribe --region us-east-1 --protocol email --notification-endpoint you@example.com \
     --topic-arn arn:aws:sns:us-east-1:<ACCOUNT_ID>:billing-alarm
   ```
   Confirm the subscription from the email you receive.
3. Create the alarm (fires when estimated month-to-date charges exceed $10):
   ```bash
   aws cloudwatch put-metric-alarm --region us-east-1 --alarm-name sandbox-over-10-usd \
     --namespace AWS/Billing --metric-name EstimatedCharges --dimensions Name=Currency,Value=USD \
     --statistic Maximum --period 21600 --evaluation-periods 1 --threshold 10 \
     --comparison-operator GreaterThanThreshold \
     --alarm-actions arn:aws:sns:us-east-1:<ACCOUNT_ID>:billing-alarm
   ```
4. Optional belt-and-braces: **AWS Budgets → Create budget → Zero spend / Monthly cost budget** at $10 with an email
   alert at 80%.

When the demo is over: `python infra/sandbox-seed/seed.py --region <region> --teardown`.
