from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType
from config import settings
import logging
import sqlite3
import time
import requests
import json
import os
import feedparser
import re

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def login():
    global lemmy
    lemmy = Lemmy("https://" + settings.INSTANCE)
    lemmy.log_in(settings.USERNAME, settings.PASSWORD)

    return lemmy

def create_table(conn, table_name, table_definition):
    curs = conn.cursor()
    curs.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} {table_definition}''')
    conn.commit()
    logging.debug(f"Checked/created {table_name} table")

def check_dbs():
    try:
        with sqlite3.connect('resources/vote.db') as conn:
            # Create or check votes table
            create_table(conn, 'votes', '(vote_id INT, username TEXT, vote_result TEXT, account_age TEXT)')

            # Create or check polls table
            create_table(conn, 'polls', '(poll_id INTEGER PRIMARY KEY AUTOINCREMENT, poll_name TEXT, username TEXT, open TEXT)')

        with sqlite3.connect('resources/users.db') as conn:
            #Create or check users table
            create_table(conn, 'users', '(local_user_id INT, public_user_id INT, username TEXT, has_posted INT, has_had_pm INT, email TEXT, subscribed INT)')

            #Create or check communities table
            create_table(conn, 'communities', '(community_id INT, community_name TEXT)')

        with sqlite3.connect('resources/games.db') as conn:
            #create or check bundles table
            create_table(conn, 'bundles', '(bundle_machine_name TEXT)')

            #create or check game deals table   
            create_table(conn, 'deals', '(deal_name TEXT, deal_date TEXT)')

        with sqlite3.connect('resources/mod_actions.db') as conn:
            #create or check new posts table
            create_table(conn, 'new_posts', '(post_id INT, poster_id INT, mod_action STR)')

            #create or check new comments table
            create_table(conn, 'new_comments', '(comment_id INT, comment_poster INT, mod_action STR)')

        with sqlite3.connect('resources/news.db') as conn:
            #create or check new posts table
            create_table(conn, 'game_news', '(article_title TEXT, article_date TEXT)')



    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    except Exception as e:
        logging.error(f"Exception in _query: {e}")
  
def connect_to_vote_db():
    return sqlite3.connect('resources/vote.db')

def connect_to_news_db():
    return sqlite3.connect('resources/news.db')

def connect_to_users_db():
    return sqlite3.connect('resources/users.db')

def execute_sql_query(connection, query, params=()):
    with connection:
        curs = connection.cursor()
        curs.execute(query, params)
        return curs.fetchone()

def add_vote_to_db(pm_username, vote_id, vote_response, pm_account_age):
    try:
        with connect_to_vote_db() as conn:
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id, poll_name FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (vote_id,))

            if check_valid is None:
                logging.debug("Submitted vote_id did not match a valid poll_id")
                return "notvalid"

            #check poll is still open
            closed_query = '''SELECT poll_id, open FROM polls where poll_id=?'''
            check_open = execute_sql_query(conn, closed_query, (vote_id,))
            if check_open[1] == "0":
                return "closed"
            
            poll_name = check_valid[1]
            # Check if vote response is already recorded for this user/vote id
            vote_query = '''SELECT vote_id, username FROM votes WHERE vote_id=? AND username=?'''
            row = execute_sql_query(conn, vote_query, (vote_id, pm_username))

            if row:
                logging.debug("Matching vote found")
                return "duplicate"

            # If no duplicate votes, add new vote
            sqlite_insert_query = """INSERT INTO votes (vote_id, username, vote_result, account_age) VALUES (?, ?, ?, ?);"""
            data_tuple = (vote_id, pm_username, vote_response, pm_account_age)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added vote to database")
            return poll_name
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"

def create_poll(poll_name, pm_username): 
    try:
        with connect_to_vote_db() as conn:
            isopen = True            
            data_tuple = (poll_name, pm_username, isopen)
            sqlite_insert_query = """INSERT INTO polls (poll_name, username, open) VALUES (?, ?, ?);"""
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            # Get the ID of the poll just created
            poll_id_query = "SELECT last_insert_rowid()"
            poll_id = execute_sql_query(conn, poll_id_query)[0]


            logging.debug("Added poll to database with ID number " + str(poll_id))
            return poll_id
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"
    
def close_poll(poll_id):
    try:
        with connect_to_vote_db() as conn:
            set_open = "0"
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (poll_id,))

            if check_valid is None:
                logging.debug("Submitted vote_id did not match a valid poll_id")
                return "notvalid"
            
            sqlite_update_query = """UPDATE polls SET open = ? WHERE poll_id = ?;"""
            execute_sql_query(conn, sqlite_update_query, (set_open, poll_id))
            return "closed"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"
    
def count_votes(poll_id):
    try:
        with connect_to_vote_db() as conn:
            yes_query = "SELECT COUNT(*) FROM votes WHERE vote_result = 'yes' AND vote_id = ?;"
            no_query = "SELECT COUNT(*) FROM votes WHERE vote_result = 'no' AND vote_id = ?;"
            yes_count = execute_sql_query(conn, yes_query, (poll_id,))[0]
            no_count = execute_sql_query(conn, no_query, (poll_id,))[0]
            return yes_count, no_count
        
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"    


def check_pms():
    try:
        pm = lemmy.private_message.list(True, 1)

        private_messages = pm['private_messages']
    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for pm in private_messages:
        pm_sender = pm['private_message']['creator_id']
        pm_username = pm['creator']['name']
        pm_context = pm['private_message']['content']
        pm_id = pm['private_message']['id']
        pm_account_age = pm['creator']['published']
    
        output = lemmy.user.get(pm_sender)
        user_score = output['person_view']['counts']['comment_score']
        user_local = output['person_view']['person']['local']
        user_admin = output['person_view']['person']['admin']

        logging.debug(pm_username + " (" + str(pm_sender) + ") sent " + pm_context + " - user score is " + str(user_score) + " " + str(user_admin))

        if user_local != settings.LOCAL:
            lemmy.private_message.create("Hey, " + pm_username + f". This bot is only for users of {settings.INSTANCE}. "
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#help":
            if user_admin == True:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#rules` - See the current instance rules. \n"
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote 1 yes` or `#vote 1 no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work!"
                                                                            "\n\n As an Admin, you also have access to the following commands: \n"
                                                                            "- `#poll` - Create a poll for users to vote on. Give your poll a name, and you will get back an ID number to users so they can vote on your poll. Example usage: `#poll @Vote for best admin` \n"
                                                                            "- `#closepoll` - Close an existing poll using the poll ID number, for example `#closepoll @1`\n" 
                                                                            "- `#countpoll` - Get a total of the responses to a poll using a poll ID number, for example `#countpoll @1` \n"
                                                                            "- `#takeover` - Add a user as a mod to an existing community. Command is `#takeover` followed by these identifiers in this order: `-community_name` then `-user_id` (use `-self` here if you want to apply this to yourself) \n"
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#rules` - See the current instance rules. \n"
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote 1 yes` or `#vote 1 no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work!"
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context == "#score":
            lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is " + str(user_score) + ". \n \n I am a Bot. If you have any "
                                                                "queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#rules":
            lemmy.private_message.create("Hey, " + pm_username + ". These are the current rules for Lemmy.zip. \n \n"
                                                                    "- Please abide by the [General Code of Conduct](https://join-lemmy.org/docs/en/code_of_conduct.html) at all times.\n"
                                                                    "- Remember the human! (no harassment, threats, etc.)\n"
                                                                    "- No racism or other discrimination\n"
                                                                    "- No endorsement of hate speech\n"
                                                                    "- No self-advertisements or spam\n"
                                                                    "- No link-spamming\n"
                                                                    "- No content against UK law.\n"
                                                                    "- Any NSFW post must be tagged as NSFW. Failure to do so will be given one warning only\n"
                                                                    "- Anything that you wouldn’t want your boss or coworkers to see, needs to be tagged NSFW\n"
                                                                    "- NSFW also acts as “Content Warning” outside of the specific NSFW communities\n\n"
                                                                    "Any posts or comments that are in breach of these rules will be dealt with, and remediation will occur. Whether that be a warning, temporary ban, or permanent ban.\n\n"
                                                                    "(TLDR) The crux of it boils down to:\n"
                                                                    "- Remember that we are all humans\n"
                                                                    "- Don’t be overtly aggressive towards anyone\n"
                                                                    "- Try and share ideas, thoughts and criticisms in a constructive way\n"
                                                                    "- Tag any NSFW posts as such"                                       
                                                                    "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


        if pm_context == "#credits":
            lemmy.private_message.create("Hey, " + pm_username + ". This bot was built with help and support from various community members and contributers: \n\n"
                                                                "- Demigodrick - Original Creator\n"
                                                                "- Sami - Support with original idea and implementation \n"
                                                                "- TheDuude (sh.itjust.works) - Refactoring of code and support with improving inital implementation \n"
                                                                "- efwis - code contributions regarding new user database \n\n"
                                                                "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#feedback":
            lemmy.private_message.create("Hey, " + pm_username + ". The access code for the feedback survey is `" + settings.SURVEY_CODE + "`. \n"
                                                                    "You can access the survey by [clicking here](https://feedback.lemmy.zip) and selecting the available survey. \n\n"
                                                                "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#unsubscribe":
            status = "unsub"
            if broadcast_status(pm_sender, status) == "successful":
                lemmy.private_message.create("Hey, " + pm_username + ". \n \n"
                                             "Your unsubscribe request was successful. You can resubscribe at any time by sending me a message with `#subscribe`. \n\n"
                                             "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". \n \n"
                                             "Sorry, something went wrong with your request :( \n\n"
                                             "Please message [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip) directly to let them know, and they'll sort it out for you.")
                
            lemmy.private_message.mark_as_read(pm_id,True)
            continue

        if pm_context == "#subscribe":
            status = "sub"
            if broadcast_status(pm_sender, status) == "successful":
                lemmy.private_message.create("Hey, " + pm_username + ". \n \n"
                                             "Your subscribe request was successful. You can unsubscribe at any time by sending me a message with `#unsubscribe`. \n\n"
                                             "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". \n \n"
                                             "Sorry, something went wrong with your request :( \n\n"
                                             "Please message [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip) directly to let them know, and they'll sort it out for you.")
                
            lemmy.private_message.mark_as_read(pm_id,True)
            continue
                       


        if pm_context.split(" @")[0] == "#create":
            community_name = pm_context.split("@")[1]

            # check user score
            if user_score < int(settings.SCORE):
                lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is too low to create a "
                                                                        "community. Please interact with other "
                                                                        "communities first. You can check your score at "
                                                                        "any time by sending me a message with `#score` "
                                                                        "and I will let you know!"  "\n \n I am a Bot. "
                                                                        "If you have any queries, please contact ["
                                                                        "Demigodrick](/u/demigodrick@lemmy.zip) or ["
                                                                        "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # check if it already exists
            check_community = lemmy.discover_community(community_name)

            if check_community is not None:
                lemmy.private_message.create("Hey, " + pm_username + ". Sorry, it looks like the community you are "
                                                                        "trying to create already exists. \n \n I am a "
                                                                        "Bot. If you have any queries, please contact ["
                                                                        "Demigodrick](/u/demigodrick@lemmy.zip) or ["
                                                                        "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # create community - add user and remove bot as mod
            lemmy.community.create(community_name, community_name)
            community_id = lemmy.discover_community(community_name)
            lemmy.community.add_mod_to_community(True, community_id, pm_sender)
            lemmy.community.add_mod_to_community(False, community_id, settings.BOT_ID)

            lemmy.private_message.create("Hey, " + pm_username + ". Your new community, [" + community_name + "](/c/" + community_name + "), has been created. You can now set this community up to your liking. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" -")[0] == "#takeover":
            if user_admin == True:
                community_name = pm_context.split("-")[1]
                user_id = pm_context.split("-")[2]
                
                if user_id == "self":
                    user_id = pm_id

                check_community = lemmy.discover_community(community_name)
                print (community_name)
                print (check_community)

                if check_community is None:
                    lemmy.private_message.create("Hey, " + pm_username + ". Sorry, I can't find the community you've requested.", pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
                
                lemmy.community.add_mod_to_community(True, community_id, user_id)
                lemmy.private_message.create("Confirmation: " + community_name + "(" + community_id + ") has been taken over by user id + " + user_id, pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
   
        if pm_context.split(" ")[0] == "#vote":
            vote_id = pm_context.split(" ")[1]
            vote_response = pm_context.split(" ")[2]

            db_response = add_vote_to_db(pm_username,vote_id,vote_response,pm_account_age) 

            if db_response == "duplicate":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It looks like you've already voted on this poll. Votes can only be counted once. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if db_response == "notvalid":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It doesn't look like the poll you've tried to vote on exists. Please double check the vote ID and try again." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if db_response == "closed":
                lemmy.private_message.create("Hey, " + pm_username + ". Sorry, it appears the poll you're trying to vote on is now closed. Please double check the vote ID and try again." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            else:
                lemmy.private_message.create("Hey, " + pm_username + ". Your vote has been counted on the '" + db_response + "' poll. Thank you for voting! " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context.split(" @")[0] == "#poll":
            if user_admin == True:
                poll_name = pm_context.split("@")[1]
                poll_id = create_poll(poll_name, pm_username) 
                lemmy.private_message.create("Hey, " + pm_username + ". Your poll has been created with ID number " + str(poll_id) + ". You can now give this ID to people and they can now cast a vote using the `#vote` operator." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". You need to be an instance admin in order to create a poll."
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
        
        if pm_context.split(" @")[0] == "#closepoll":
            if user_admin == True:
                poll_id = pm_context.split("@")[1]
                if close_poll(poll_id) == "closed":
                    lemmy.private_message.create("Hey, " + pm_username + ". Your poll (ID = " + poll_id + ") has been closed"
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
                else:
                    lemmy.private_message.create("Hey, " + pm_username + ". I couldn't close that poll due to an error."
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
        
        if pm_context.split(" @")[0] == "#countpoll":
            if user_admin == True:
                poll_id = pm_context.split("@")[1]
                yes_votes, no_votes = count_votes(poll_id)
                lemmy.private_message.create("Hey, " + pm_username + ". There are " + str(yes_votes) + " yes votes and " + str(no_votes) + " no votes on that poll."
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        #broadcast messages
        if pm_context.split(" ")[0] == "#broadcast":
            if user_admin == True:
                message = pm_context.replace('#broadcast', "", 1)
                broadcast_message(message)                
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#purgevotes":
            if user_admin == True:
               if os.path.exists('resources/vote.db'):
                    os.remove('resources/vote.db')
                    check_dbs()
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context == "#purgeadminactions":
            if user_admin == True:
                if os.path.exists('resources/mod_actions.db'):
                    os.remove('resources/mod_actions.db')
                    check_dbs()
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

        #keep this at the bottom
        else:
            lemmy.private_message.create("Hey, " + pm_username + ". Sorry, I did not understand your request. Please "
                                                                 "try again or use `#help` for a list of commands. \n "
                                                                 "\n I am a Bot. If you have any queries, "
                                                                 "please contact [Demigodrick]("
                                                                 "/u/demigodrick@lemmy.zip) or [Sami]("
                                                                 "/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

def is_spam_email(email, spam_domains):
    # Split the email address at '@' and take the second half (i.e., the domain)
    domain = email.split('@')[1]
    logging.info("Checking spam email with domain: " + domain)
    # Check if the domain is in the list of spam domains
    return domain in spam_domains

def get_new_users():
    spam_domains = set()  # Initialize an empty set

    # Read in the list of spam domains from a file
    with open('resources/disposable_email_blocklist.conf', 'r') as file:
        for line in file:
            spam_domains.add(line.strip())  # Add each domain to the set

    try:
        output = lemmy.admin.list_applications(unread_only="true")
        new_apps = output['registration_applications']
    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for output in new_apps:
        local_user_id = output['registration_application']['local_user_id']
        username = output['creator']['name']
        email = output['creator_local_user']['email']
        public_user_id = output['creator_local_user']['person_id']
       
        if update_registration_db(local_user_id, username, public_user_id, email) == "new_user":
            logging.debug("sending new user a pm")
            lemmy.private_message.create("Hey, " + username + ". \n \n # Welcome to Lemmy.zip! \n \n Please take a moment to familiarise yourself with [our Welcome Post](https://lemmy.zip/post/43). (Text that looks like this is a clickable link!) \n \n" 
                                                                "This post has all the information you'll need to get started on Lemmy, so please have a good read first! \n \n"
                                                                "Please also take a look at our rules, they are in the sidebar of this instance. I can send these to you at any time, just reply to this message or send me a new message with `#rules`. \n \n"
                                                                "If you're on a mobile device, you can [tap here](https://m.lemmy.zip) to go straight to our mobile site. \n \n"
                                                                "Lemmy.zip is 100% funded by user donations, so if you are enjoying your time on Lemmy.zip please [consider donating](https://opencollective.com/lemmyzip).\n \n"
                                                                "Want to change the theme of the site? You can go to your [profile settings](https://lemmy.zip/settings) (or click the dropdown by your username and select Settings) and scroll down to theme. You'll find a list of themes you can try out and see which one you like the most! \n \n"
                                                                "You can also set a Display Name that is different from your account username by updating the Display Name field. By default, your Display Name will show up to other users as `@your_username`, but by updating this field it will become whatever you want it to be! \n \n"
                                                                "If you'd like more help, please reply to this message with `#help` for a list of things I can help with. \n \n"
                                                                "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip) via email to `hello@lemmy.zip`. Beep Boop. ", public_user_id)
            
            # Check if the email is from a known spam domain     
            if is_spam_email(email, spam_domains):
                logging.info("User " + username + " tried to register with a spam email: " + email)
                lemmy.private_message.create("Hello, new user " + username + " with ID " + str(public_user_id) + " has signed up with a temporary/spam email address (" + email + "). Please manually review before approving.", 2)
                lemmy.private_message.create("Hello, new user " + username + " with ID " + str(public_user_id) + " has signed up with a temporary/spam email address (" + email + "). Please manually review before approving.", 16340)   

            if settings.EMAIL_FUNCTION == True:    
                welcome_email(email)

        continue

def update_registration_db(local_user_id, username, public_user_id, email):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            #search db for matching user id
            curs.execute('SELECT local_user_id FROM users WHERE local_user_id=?', (local_user_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching ID found, ignoring")
                return "User ID already exists"
            
            #default user to subscribed list
            subscribed = 1

            logging.debug("User ID did not match an existing user ID, adding")       
            sqlite_insert_query = "INSERT INTO users (local_user_id, public_user_id, username, email, subscribed) VALUES (?, ?, ?, ?, ?);"
            data_tuple = (local_user_id, public_user_id, username, email, subscribed)
            
            curs.execute(sqlite_insert_query, data_tuple)
            logging.debug("Added new user to database")
            return "new_user"
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"
    
def get_communities():
    try:
        communities = lemmy.community.list(limit=5, page=1, sort=SortType.New, type_=ListingType.Local)
        local_comm = communities

    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for communities in local_comm:
        community_id = communities['community']['id']
        community_name = communities['community']['name']
        
        find_mod = lemmy.community.get(community_id)

        if find_mod.get('moderators') is None:
            logging.info("Unable to get moderator of community, skipping.")
            continue

        mods = find_mod['moderators']

        #throwing this in here to help stop nginx timeouts causing errors
        time.sleep(0.5)

        for find_mod in mods:
            mod_id = find_mod['moderator']['id']
            mod_name = find_mod['moderator']['name']

        if new_community_db(community_id, community_name) == "community":
            lemmy.private_message.create("Hey, " + mod_name + ". Congratulations on creating your community, [" + community_name + "](/c/"+community_name+"@lemmy.zip). \n Here are some tips for getting users to subscribe to your new community!\n"
                                                                "- Try posting a link to your community at [New Communities](/c/newcommunities@lemmy.world).\n"
                                                                "- Ensure your community has some content. Users are more likely to subscribe if content is already available. (5 to 10 posts is usually a good start)\n"
                                                                "- Consistency is key - you need to post consistently and respond to others to keep engagement with your new community up.\n\n"
                                                                "I hope this helps!"
                                                                "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", mod_id)    


def new_community_db(community_id, community_name):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            #search db to see if community exists in DB already
            curs.execute('SELECT community_id FROM communities WHERE community_id=?', (community_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching community ID found, ignoring")
                return "Community ID already exists"

            logging.debug("community ID did not match an existing community ID, adding")       
            sqlite_insert_query = "INSERT INTO communities (community_id, community_name) VALUES (?, ?);"
            data_tuple = (community_id, community_name)
            
            curs.execute(sqlite_insert_query, data_tuple)
            logging.debug("Added new community to database")
            return "community"
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"
    
def humblebundle():
    response = requests.get("https://www.humblebundle.com/client/bundles")
    bundles = json.loads(response.text)
    for bundle in bundles:
        bundle_url = bundle['url']
        bundle_name = bundle['bundle_name']
        bundle_machine_name = bundle['bundle_machine_name']

        if (".com/games" not in bundle_url) and (".com/membership" not in bundle_url):
            continue

        #add or check bundle in db
        if add_bundle_to_db(bundle_machine_name) == "added":
            #add bundle to website
            community_id = lemmy.discover_community("gamedeals")
            lemmy.post.create(community_id,name="Humble Bundle: " + bundle_name, url=bundle_url)


def connect_to_games_db():
    return sqlite3.connect('resources/games.db')

def add_bundle_to_db(bundle_machine_name):
    try:
        with connect_to_games_db() as conn:
            # Check if bundble already is in db
            bundle_query = '''SELECT bundle_machine_name FROM bundles WHERE bundle_machine_name=?'''
            bundle_match = execute_sql_query(conn, bundle_query, (bundle_machine_name,))

            if bundle_match:
                return "duplicate"

            logging.debug("New bundle to be added to DB")
            
            sqlite_insert_query = """INSERT INTO bundles (bundle_machine_name) VALUES (?);"""
            data_tuple = (bundle_machine_name,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added bundle to database")
            return "added"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"
    

def welcome_email(email):
    message = MIMEMultipart()
    message['From'] = settings.SENDER_EMAIL
    message['To'] = email
    message['Subject'] = "Thanks for signing up to Lemmy.zip!"

    #use this for a simple text email, uncomment below:
    #body
    #body = "Thanks for signing up to Lemmy.zip.\n\n We've received your application and one of our Admins will manually verify your account shortly. \n\n Lemmy.zip prides itself on being a welcoming and inclusive Lemmy instance, and to help reduce spam we manually verify all accounts.\n\n Once your account is accepted, you will receive another email from us confirming this and then you'll be able to log in to your account using the details you set up. You won't be able to login until you've received this confirmation email.\n\n If you've not received an email confirming you have been accepted within a couple of hours, please email hello@lemmy.zip with your username, and we can look into the issue further. Please be patient with us!\n\n Thanks again for signing up to Lemmy.zip, we're excited to welcome you to the Fediverse :)\n\n PS - Once you've logged in, look out for a message from ZippyBot with a guide on how to get started!"
    #message.attach(MIMEText(body, 'plain'))

    #use this for sending a HTML email i.e. with pictures and colours.
    #html email - resources to be saved in the "resources" folder
    with open('resources/index.html', 'r', encoding='utf-8') as html_file:
        html_content = html_file.read()
    # Attach the HTML content to the email
    message.attach(MIMEText(html_content, 'html'))

    # Attach the image as an inline attachment
    with open('resources/images/image-1.png', 'rb') as image_file:
        image = MIMEImage(image_file.read())
        #use content ids and change to img tag in html to match
        image.add_header('Content-ID', '<image-1>') 
        message.attach(image)

    with open('resources/images/image-2.png', 'rb') as image_file:
        image = MIMEImage(image_file.read())
        image.add_header('Content-ID', '<image-2>')
        message.attach(image)

    #initialise SMTP server - keep from here for either email type.
    try:
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
        server.sendmail(settings.SENDER_EMAIL, email, message.as_string())
        logging.info("Welcome email sent successfully")
    except Exception as e:
        logging.error("Error: Unable to send email.", str(e))
    finally:
        server.quit


def game_deals():
    # URL of the RSS feed
    rss_url = "https://isthereanydeal.com/rss/specials/"

    # Parse the RSS feed
    feed = feedparser.parse(rss_url)
    
    # Loop through the entries in the feed
    for entry in feed.entries[:10]:
        if "humblebundle.com" not in entry.link and "[voucher]" not in entry.title:
            deal_title = entry.title
            deal_published = entry.published
            deal_link = entry.link

            if add_deal_to_db(deal_title, deal_published) == "added":
                #add bundle to website
                community_id = lemmy.discover_community("gamedeals")
                lemmy.post.create(community_id,name="Game Deal: " + deal_title, url=deal_link)


def steam_deals():
    #url of the RSS Feed
    rss_url = "http://www.reddit.com/r/steamdeals/new/.rss?sort=new"

    #parse feed
    feed = feedparser.parse(rss_url)

    #loop through 10 entries
    for entry in feed.entries[:10]:
        content_value = entry.content[0]['value']
        steam_url = re.search(r'https://store.steampowered.com/app/\d+/\w+/', str(content_value))
        
        deal_published = entry.published
        deal_title = entry.title

        if steam_url:
            steam_url = steam_url.group()
        else:
            logging.info("No store.steampowered.com URL found in the steam deals entry.")
            add_deal_to_db(deal_title, deal_published)
            continue
        
        
        if add_deal_to_db(deal_title, deal_published) == "added":
            community_id = lemmy.discover_community("gamedeals")
            lemmy.post.create(community_id,name="Steam Deal: " + deal_title, url=steam_url)

def game_news():
    #url of rss feed
    rss_url = "https://www.gameinformer.com/news.xml"

    feed = feedparser.parse(rss_url)
    for entry in feed.entries[:10]:
        article_title = entry.title
        article_date = entry.published
        article_url = entry.link

        if add_news_to_db(article_title, article_date) == "added":
            #add news to website
            community_id = lemmy.discover_community("gaming")
            lemmy.post.create(community_id, article_title, url=article_url)

def add_news_to_db(article_title, article_date):
    try:
        with connect_to_news_db() as conn:
            #check if news article was already published
            news_query = '''SELECT article_title, article_date FROM game_news WHERE article_title=? AND article_date=?'''
            news_match = execute_sql_query(conn, news_query, (article_title,article_date,))

            if news_match:
                return "duplicate"

            logging.debug("New news article")

            sqlite_insert_query = '''INSERT INTO game_news (article_title, article_date) VALUES (?,?);'''
            data_tuple = (article_title, article_date,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added news article to db")
            return "added"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"


def add_deal_to_db(deal_title, deal_published):            
    try:
        with connect_to_games_db() as conn:
            # Check if bundble already is in db
            deal_query = '''SELECT deal_name, deal_date FROM deals WHERE deal_name=? AND deal_date=?'''
            deal_match = execute_sql_query(conn, deal_query, (deal_title,deal_published,))

            if deal_match:
                return "duplicate"

            logging.debug("New deal to be added to DB")
            
            sqlite_insert_query = """INSERT INTO deals (deal_name, deal_date) VALUES (?,?);"""
            data_tuple = (deal_title, deal_published,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added deal to database")
            return "added"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"
    
def check_comments():
    recent_comments = lemmy.comment.list(limit=10,type_=ListingType.Local)
    for comment in recent_comments:
        comment_id = comment['comment']['id']
        comment_text = comment['comment']['content']
        comment_poster = comment['comment']['creator_id']

        #check if it has already been scanned
        if check_comment_db(comment_id) == "duplicate":
            continue
        
        regex_pattern = r'((f(a|4)g(got|g)?){1,}|ni((g{2,}|q)+|[gq]{2,})[e3r]+(s|z)?|dindu(s?){1,}|mudslime?s?|kikes?|\bspi(c|k)s?\b|\bchinks?|gooks?|\btr(a|@)nn?(y|(i|1|l)es?|ers?)|(tr(a|@)nn?(y|(i|1|l)es?|ers?)){1,}|(towel\s*heads?){1,}|be(a|@|4)ners?|\bjaps?\b|(japs){2,}|\bcoons?\b|(coons?){2,}|\bpakis?\b|(pakis?){2,}|(porch\s?monkey){1,}|\bching\s?chong\b|(ching\s?chong\s?){1,}|(curry\s?munchers?))'
        if re.search(regex_pattern,comment_text):
            #matching word found
            lemmy.comment.report(comment_id,reason="Word in comment appears on slur list - Automated report by ZippyBot")
            mod_action = "Comment Flagged"
            logging.info("Word matching regex found in content, reported.")
        else:
            mod_action = "None"
        
        add_comment_to_db(comment_id, comment_poster, mod_action)

def check_comment_db(comment_id):
    try:
        with connect_to_mod_db() as conn:
            action_query = '''SELECT comment_id FROM new_comments WHERE comment_id=?'''
            comment_match = execute_sql_query(conn, action_query, (comment_id,))

            if comment_match:
                return "duplicate"   
                
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"

def add_comment_to_db(comment_id, comment_poster, mod_action):
    try:          
        logging.debug("Adding new comment to db")
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO new_comments (comment_id, comment_poster, mod_action) VALUES (?,?,?);"""
            data_tuple = (comment_id, comment_poster, mod_action,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added comment to db")
            return "added"
        
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"
    
def connect_to_mod_db():
    return sqlite3.connect('resources/mod_actions.db')

def check_posts():
    recent_posts = lemmy.post.list(limit=10,type_=ListingType.Local)
    for post in recent_posts:
        post_id = post['post']['id']
        post_title = post['post']['name']
        # Check if 'body' exists in the 'post' dictionary
        if 'body' in post['post']:
            post_text = post['post']['body']
        else:
            post_text = "No body found" 
        
        poster_id = post['creator']['id']
        poster_name = post['creator']['name']

        #check if post has already been scanned
        if check_post_db(post_id) == "duplicate":
            continue

        regex_pattern = r'((f(a|4)g(got|g)?){1,}|ni((g{2,}|q)+|[gq]{2,})[e3r]+(s|z)?|dindu(s?){1,}|mudslime?s?|kikes?|\bspi(c|k)s?\b|\bchinks?|gooks?|\btr(a|@)nn?(y|(i|1|l)es?|ers?)|(tr(a|@)nn?(y|(i|1|l)es?|ers?)){1,}|(towel\s*heads?){1,}|be(a|@|4)ners?|\bjaps?\b|(japs){2,}|\bcoons?\b|(coons?){2,}|\bpakis?\b|(pakis?){2,}|(porch\s?monkey){1,}|\bching\s?chong\b|(ching\s?chong\s?){1,}|(curry\s?munchers?))'
        match_found = False

        if re.search(regex_pattern,post_text):
            match_found = True
        if re.search(regex_pattern,post_title):
            match_found = True

        if match_found == True:
            #matching word found
            lemmy.post.report(post_id,reason="Word in post by user " + poster_name + " appears on slur list - Automated report by ZippyBot")
            mod_action = "Post Flagged"
            logging.info("Word matching regex found in content, reported.")
        else:
            mod_action = "None"
        
        add_post_to_db(post_id, poster_id, mod_action)


def check_post_db(post_id):
    try:
        with connect_to_mod_db() as conn:
            action_query = '''SELECT post_id FROM new_posts WHERE post_id=?'''
            post_match = execute_sql_query(conn, action_query, (post_id,))

            if post_match:
                return "duplicate"   
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"

def add_post_to_db(post_id, poster_id, mod_action):
    try:          
        logging.debug("Adding new post to db")
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO new_posts (post_id, poster_id, mod_action) VALUES (?,?,?);"""
            data_tuple = (post_id, poster_id, mod_action,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added post to db")
            return "added"
        
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return "error"

def broadcast_message(message):
    #get lowest and highest local user ids first
    try:
        logging.debug("broadcasting message")
        with connect_to_users_db() as conn:
            cursor = conn.cursor()
            query = "SELECT public_user_id, username, subscribed FROM users ORDER BY local_user_id"
            cursor.execute(query)
                
            for row in cursor.fetchall():
                public_id, username, subscribed = row
                try:
                    if subscribed == 1:
                        lemmy.private_message.create("Hello, " + username + ".\n \n" + message + "\n\n *This is an automated message. To unsubscribe, please reply to this message with* `#unsubscribe`.", public_id) 
                        time.sleep(0.2)
                except Exception as e:
                    logging.exception("Message failed to send to " + username)
    except sqlite3.Error as e:
        logging.error("SQLite error: %s", e)               

    finally:
        if cursor:
            cursor.close()

def broadcast_status(pm_sender, status):
    with connect_to_users_db() as conn:
        cursor = conn.cursor()
        
        if status == "unsub":    
            query = "UPDATE users SET subscribed = 0 WHERE public_user_id = ?"
            cursor.execute(query, (pm_sender,))
            conn.commit()  # Committing the transaction
            logging.debug("User unsubscribed successfully")
            return "successful"


        if status == "sub":
            query = "UPDATE users SET subscribed = 1 WHERE public_user_id = ?"
            cursor.execute(query, (pm_sender,))
            conn.commit()  # Committing the transaction
            logging.debug("User subscribed successfully")
            return "successful"
    

