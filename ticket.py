import os
import logging ,json, sys
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests

# Configure the logging module
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler('/appz/log/slackbot.log', mode='a', encoding='utf-8')]
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# BOT_TOKEN should be set as an environment variable with your bot's token
bot_token = os.environ.get("BOT_TOKEN")
app_token = os.environ.get("APP_TOKEN")
mantis_url = os.environ.get("MANTIS_URL")
mantis_token = os.environ.get("MANTIS_TOKEN")
channel_id = os.environ.get("CHANNEL_ID")

if bot_token is None or app_token is None:
    logging.error("BOT_TOKEN not set as an environment variable")
    sys.exit(1)

if mantis_url is None or mantis_token is None:
    logging.error("MANTIS_URL and MANTIS_TOKEN not set as environment variables")
    sys.exit(1)

if channel_id is None:
    logging.error("CHANNEL_ID not set as an environment variable")
    sys.exit(1)

def load_issue(issues_file):
    try:
        with open(issues_file, 'r') as file:
            data = json.load(file)
            issue_data = data.get('issues', [])
            update_data = data.get('updates', [])
            json_issue = json.dumps(issue_data, indent=4)
            json_update = json.dumps(update_data, indent=4)
            logger.info('Loaded issues: {}, Loaded updates={}'.format(json_issue, json_update))
            return json_issue, json_update
    except Exception as err:
        logger.error("Failed to load issue.{}".format(err))
        sys.exit(1)

def create_mantis_issue(original_message):
    # data = json.loads(load_issue("/appz/scripts/issues.json"))[0]
    # data["summary"] = original_message
    json_issue, _ = load_issue("/appz/scripts/issues.json") 
    data = json.loads(json_issue)[0]
    data["summary"] = original_message
    payload = json.dumps(data, indent=4)
    logging.info(f"data:{payload}") 
    
    url = f"{mantis_url}/api/rest/issues"
    headers = {
        'Authorization': mantis_token,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        
        logging.info("Issue created successfully")
    except Exception:
        logging.error(f"Failed to create the issue: {response.status_code} {response.reason}")
        logging.error("Exception handled, ", exc_info=True) 

def modify_mantis_ticket(issue_id, original_message, handler):
    _, json_update = load_issue("/appz/scripts/issues.json")
    data = json.loads(json_update)[0]
    #name_value = data["notes"][0]["reporter"]["name"]
    text_value = "{} @{} @CSM".format(original_message, handler)
    data["notes"][0]["text"] = text_value
    payload = json.dumps(data, indent=4)
    logging.info(f"data:{payload}") 

    url = f"{mantis_url}/api/rest/issues/{issue_id}"
    headers = {
        'Authorization': mantis_token,
        'Content-Type': 'application/json'
    }
    try:
        response = requests.patch(url, headers=headers, data=payload)
        response.raise_for_status() 

        logging.info("Issue modified successfully")
    except Exception:
        logging.error("Exception handled, ", exc_info=True) 
        
        
def get_mantis_filters(original_message):
    url = f"{mantis_url}/api/rest/filters"
    headers = {
        'Authorization': mantis_token
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() 

        # Log a successful response
        logging.info(f"Successful MantisBT get filters response: {response.status_code} {response.reason}")
        filters_data = response.json()
        for filter in filters_data["filters"]:
            filter_name = filter["name"]
            filter_id = filter["id"]
            if filter_name in original_message:
                return filter_id
            else:
                filter_name not in original_message
                logging.info("filter {} not matching:{}".format(filter_name, original_message))
    except Exception:
        logging.error("Exception handled, ", exc_info=True)
        return None
    

def get_issues_by_filter_id(filter_id, original_message):
    url = f"{mantis_url}/api/rest/issues?filter_id={filter_id}"
    #logging.info("filter_id:{}".format(filter_id))
    headers = {
        'Authorization': mantis_token
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() 

        # Log a successful response
        logger.info("Successful MantisBT get issues response: {} {}".format(response.status_code, response.reason))
        issue_data = response.json()
        match_issue = ""
        for issue in issue_data["issues"]:
            if isinstance(issue, dict):
                #logging.info('this is dict')
                logging.info('summary: {}'.format(issue.get("summary")))
                issue_id = issue["id"]
                if issue.get("summary") == original_message:
                    match_issue = issue
                    handler = match_issue["handler"]["name"]
                    logging.info("ticket exists")
                    modify_mantis_ticket(issue_id, original_message, handler)
                    break
            elif isinstance(issue, str):
                logging.info('No summary available for: {}'.format(original_message))
            else:
                logging.warning(f"Unexpected data type: {type(issue)}")
        if match_issue:
            return match_issue
        else:
            logging.info("creating new ticket")
            create_mantis_issue(original_message)
                
    except Exception:
        logging.error("Exception handled, ", exc_info=True)
        return None

try:
    app = App(token=bot_token)
    recent_messages_cache = {}
except Exception as err:
    logger.error('{}'.format(err))
else:
    app.debug = True

@app.event("message")
def handle_message(body, message):
    logger.info(f"Received message: {message}")
    event_data = body["event"]
    event_channel = body['event']['channel']
    event_ts = body['event']['event_ts']
    original_message = message['text']
    #user_id = event_data["user"]
    #text = event_data.get("text", "")
    if event_channel in channel_id:
        try:
            filters_id = get_mantis_filters(original_message)
            logger.info("get filter successful")
            issues = get_issues_by_filter_id(filters_id, original_message)
            logger.info("get issue successful")
            if issues:
                app.client.chat_postMessage(channel=channel_id, text=f"Matching issues:\n{issues}",thread_ts=event_ts)
            else:
                app.client.chat_postMessage(channel=channel_id, text=f"No issues found for {original_message}",thread_ts=event_ts)
   
        except Exception:
            logging.error("Exception handled, ", exc_info=True)

def filter_messages(body, message):
    if message['channel'] in channel_id:
        handle_message(body, message)


if __name__ == "__main__":
    SocketModeHandler(app, app_token).start()
