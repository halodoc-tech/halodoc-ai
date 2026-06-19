import os
from slack_sdk import WebClient
import requests


def send_slack_alert(MESSAGE):
    """
      This function sends a Slack alert to the specified channel using a provided Slack token.

      Args:
          :param MESSAGE: Message to send in the Slack alert.
    """
    SLACK_TOKEN = os.environ['SLACK_TOKEN']
    CHANNEL_ID = "C02BM4FDJTG"  # datalake-prod-alerts channel id
    client = WebClient(token=SLACK_TOKEN)
    try:
        response = client.chat_postMessage(channel=CHANNEL_ID, text=MESSAGE)
        print(f"Sent Slack alert successfully. Response: {response}")
    except Exception as e:
        raise Exception(f"Failed to send Slack alert: {e}")
    
def send_gchat_alert(MESSAGE):
    """
      This function sends a Google Chat alert to the specified channel using a provided gchat space webhook url.
      Args:
          :param MESSAGE: Message to send in the Google Chat alert.
    """
    webhook_url = "<gchat-webhook-url>"

    message = {
        "text": MESSAGE
    }
    try:
        response = requests.post(webhook_url, json=message)
        print(response.status_code, response.text)
    except Exception as e:
        raise Exception(f"Failed to send Google Chat alert: {e}")



