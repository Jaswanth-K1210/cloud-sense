# CloudSense

An AWS cost agent that learns your organization's unwritten rules from every rejected recommendation.

(Full README is written in a later step.)

## Slack review loop

1. Create a Slack app, enable **Socket Mode**, add bot scopes `chat:write`, `chat:write.public`, and enable
   Interactivity. Invite the bot to the review channel.
2. Set `SLACK_BOT_TOKEN` (xoxb-…), `SLACK_APP_TOKEN` (xapp-…, `connections:write`) and `SLACK_REVIEW_CHANNEL`.
3. Map reviewers: set `users.slack_id` for each reviewer/admin (the demo seed uses `U00REVIEW`).
4. Start the interactive worker: `python -m backend.review.slack_app`.
   The API process posts new pending/asked candidates to the channel after each scan when `SLACK_BOT_TOKEN` is set.
