from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType, FeatureType
from config import settings
from datetime import datetime, timedelta, timezone
import logging
import sqlite3
import time
import requests
import json
import os
import feedparser
import re
import asyncio
from nio import AsyncClient, MatrixRoom, RoomMessageText
import pytz

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

####################### N O T E S ###############################
#  Add in reports for messages (doesnt exist in pythorhead yet)
#  anti-spam measure for an ID?
#  Check applications for declined applications, send email confirming declined. 
#  Use reason if included otherwise generic text.


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
        
        with sqlite3.connect('resources/reports.db') as conn:
            create_table(conn, 'post_reports', '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, post_id INT)')

            create_table(conn, 'comment_reports', '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, comment_id INT)')

            #create_table(conn, 'message_reports', '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, message_id INT)')

        with sqlite3.connect('resources/autopost.db') as conn:
            create_table(conn, 'com_posts', '(pin_id INTEGER PRIMARY KEY AUTOINCREMENT, community_id INT, mod_id INT, post_title TEXT, post_url TEXT, post_body TEXT, scheduled_post TIME, frequency TEXT, previous_post INT)')


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

def connect_to_reports_db():
    return sqlite3.connect('resources/reports.db')

def connect_to_autopost_db():
    return sqlite3.connect('resources/autopost.db')

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

def add_autopost_to_db(post_data):
    try:
        with connect_to_autopost_db() as conn:
            cursor = conn.cursor()
            query = """
            INSERT INTO com_posts (community_id, mod_id, post_title, post_url, post_body, frequency, scheduled_post) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            values = (
                post_data['community'], 
                post_data['mod_id'], 
                post_data['title'], 
                post_data['url'], 
                post_data['body'],
                post_data['frequency'], 
                post_data['scheduled_post']
            )
            cursor.execute(query, values)
            conn.commit()

            #Get the ID of the autopost just created
            autopost_id_query = "SELECT last_insert_rowid()"
            autopost_id = execute_sql_query(conn, autopost_id_query)[0]
            return autopost_id
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"
    
def delete_autopost(pin_id, pm_sender):
    try:
        with connect_to_autopost_db() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM com_posts WHERE pin_id = ?"
            cursor.execute(query, (pin_id,))
            full_row = cursor.fetchone()

            community_name = full_row[1]
            mod_id = full_row[2]

            #check it has not already been deleted
            if community_name == None:
                lemmy.private_message.create("Hey, " + pm_username + ". A scheduled post with this ID does not exist."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                return "not deleted"   

            #check if delete request came from original author
            if mod_id == pm_sender:
                query = "DELETE FROM com_posts WHERE pin_id = ?"
                cursor.execute(query, (pin_id,))
                conn.commit 
                return "deleted"

            #not a match, check if sender is a mod of the community
            output = lemmy.community.get(name=community_name)

            is_moderator = False

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == pm_sender:
                    is_moderator = True
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (pin_id,))
                    conn.commit
                    return "deleted"

            if not is_moderator:
                # If pm_sender is not a moderator, send a private message
                lemmy.private_message.create("Hey, " + pm_username + ". As you are not the moderator of this community, you are not able to delete a scheduled post for it."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                return "not deleted"       

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
        user_local = output['person_view']['person']['local']
        user_admin = output['person_view']['is_admin']

        #open to anyone on lemmy. handles urgent mod reports.
        split_context = pm_context.split(" -")

        # Check if the first part of the split contains '#urgent'
        if "#urgent" in split_context[0] or "> #urgent" in split_context[0]:
            if len(split_context) > 1:
                context_identifier = split_context[1]
                
                if context_identifier == "p":
                    report_id = split_context[2]

                    with connect_to_reports_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT report_id, reporter_id, reporter_name, report_reason, post_id FROM post_reports WHERE report_id = ?", (report_id,))
                        row = cursor.fetchone()

                        if row:
                            report_id, reporter_id, reporter_name, report_reason, post_id = row

                            #check reporter_id matches pm_sender to stop someone spamming id numbers
                            if reporter_id == pm_sender:
                            #write message to send to matrix
                                matrix_body = "Hello, there has been an urgent report from " + reporter_name + " regarding a post at https://lemmy.zip/post/" + str(post_id) + ". The user gave the report reason: " + report_reason + " - Please review urgently."
                                asyncio.run(send_matrix_message(matrix_body))
                                lemmy.private_message.create("Hey " + pm_username +", thanks for the urgent report - We'll get right on it. "
                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                                lemmy.private_message.mark_as_read(pm_id, True)
                            else:
                                lemmy.private_message.mark_as_read(pm_id, True)



                            conn.close
                            continue
                
                if context_identifier == "c":
                    report_id = split_context[2]

                    with connect_to_reports_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT report_id, reporter_id, reporter_name, report_reason, comment_id FROM comment_reports WHERE report_id = ?", (report_id,))
                        row = cursor.fetchone()

                        if row:
                            report_id, reporter_id, reporter_name, report_reason, comment_id = row

                            #check reporter_id matches pm_sender to stop someone spamming id numbers
                            if reporter_id == pm_sender:
                            #write message to send to matrix
                                matrix_body = "Hello, there has been an urgent report from " + reporter_name + " regarding a comment at https://lemmy.zip/comment/" + str(comment_id) + ". The user gave the report reason: " + report_reason + " - Please review urgently."
                                asyncio.run(send_matrix_message(matrix_body))
                                lemmy.private_message.create("Hey " + pm_username +", thanks for the urgent report - We'll get right on it. "
                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                                lemmy.private_message.mark_as_read(pm_id, True)
                            else:
                                lemmy.private_message.mark_as_read(pm_id, True)



                            conn.close
                            continue

            else:
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            
            
        

        #IMPORTANT keep this here - only put reply code above that you want ANYONE ON LEMMY/FEDIVERSE TO BE ABLE TO ACCESS outside of your instance when they message your bot.
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
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote 1 yes` or `#vote 1 no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work! \n"
                                                                            "- `#autopost` - If you moderate a community, you can schedule an automatic post using this option. Use `#autoposthelp` for a full command list."
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
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote 1 yes` or `#vote 1 no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work! \n"
                                                                            "- `#autopost` - If you moderate a community, you can schedule an automatic post using this option. Use `#autoposthelp` for a full command list."
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

        if pm_context == "#autoposthelp":
            lemmy.private_message.create("Hey, " + pm_username + ". These are the commands you'll need to schedule an automatic post. Remember, you'll need to be a moderator in the community otherwise this won't work. \n \n"
                                                                    "A typical command would look like `#autopost -c community_name -t post_title -b post_body -d day -h time -f frequency` \n"
                                                                    "- `-c` - This defines the name of the community you are setting this up for. This is the original name of the community when you created it. \n"
                                                                    "- `-t` - This defines the title of the post. You can use the modifiers listed below here. \n"
                                                                    "- `-b` - This is the body of your post. This field is optional, so you don't need to include it if you don't want a body to your post. You can use the modifiers listed below here too. \n"
                                                                    "- `-u` - This defines a URL you can add to your post. This field is optional, so you don't need to include it. \n"
                                                                    "- `-d` - This defines the day of the week you want your thread to be posted on, i.e. `monday`, or you can enter a date you want the first post to occur in YYYYMMDD format, i.e. `20230612` which would be 12th June 2023. \n"
                                                                    "- `-h` - This defines the time of the day you want this thread to be posted, i.e. `12:00`. All times are UTC! \n"
                                                                    "- `-f` - This defines how often your thread will be posted. The options that currently exist are `weekly`, `fortnightly`, or `4weekly`. \n\n"
                                                                    "There are some modifiers you can use as outlined above: \n"
                                                                    "- `%d` - This will be replaced by the day of the month, i.e. `12` \n"
                                                                    "- `%m` - This will be replaced by the name of the month, i.e. `June`. \n"
                                                                    "- `%y` - This will be replaced by the current year, i.e. `2024` \n"
                                                                    "- `%w` - This will be replaced by the day of the week, i.e. `Monday`.\n\n"
                                                                    "For example, having `-t Weekly Thread %d %m` might be created as `Weekly Thread 12 June` depending on the day it is posted. \n\n"
                                                                    "Finally, if you want to delete a scheduled autopost, use the command `#autopostdelete` with the ID number of the autopost, i.e. `#autopostdelete 1`. "
                                                                    "\n \n If you need any further help getting this working, please contact [Demigodrick](/u/demigodrick@lemmy.zip).", pm_sender)
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
                       


        #if pm_context.split(" @")[0] == "#create":
        #    community_name = pm_context.split("@")[1]

            # check user score
        #    if user_score < int(settings.SCORE):
        #        lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is too low to create a "
        #                                                                "community. Please interact with other "
        #                                                                "communities first. You can check your score at "
        #                                                                "any time by sending me a message with `#score` "
        #                                                                "and I will let you know!"  "\n \n I am a Bot. "
        #                                                                "If you have any queries, please contact ["
        #                                                                "Demigodrick](/u/demigodrick@lemmy.zip) or ["
        #                                                                "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
        #        lemmy.private_message.mark_as_read(pm_id, True)
        #        continue
        #
            # check if it already exists
        #    check_community = lemmy.discover_community(community_name)
        #
        #    if check_community is not None:
        #        lemmy.private_message.create("Hey, " + pm_username + ". Sorry, it looks like the community you are "
        #                                                                "trying to create already exists. \n \n I am a "
        #                                                                "Bot. If you have any queries, please contact ["
        #                                                                "Demigodrick](/u/demigodrick@lemmy.zip) or ["
        #                                                                "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
        #        lemmy.private_message.mark_as_read(pm_id, True)
        #        continue

            # create community - add user and remove bot as mod
        #    lemmy.community.create(community_name, community_name)
        #    community_id = lemmy.discover_community(community_name)
        #    lemmy.community.add_mod_to_community(True, community_id, pm_sender)
        #    lemmy.community.add_mod_to_community(False, community_id, settings.BOT_ID)

        #    lemmy.private_message.create("Hey, " + pm_username + ". Your new community, [" + community_name + "](/c/" + community_name + "), has been created. You can now set this community up to your liking. " 
        #                                                         "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
        #    lemmy.private_message.mark_as_read(pm_id, True)
        #    continue

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

        #mod action - pin a post
        if pm_context.split(" ")[0] == '#autopost':
             # Define the pattern to match each qualifier and its following content
            pattern = r"-(c|t|b|u|d|h|f) (.*?)(?=\s-\w|$)"
            
            # Use regex to find all matches
            matches = re.findall(pattern, pm_context)

            # Dictionary to hold the parsed data
            post_data = {
                'community': None,
                'mod_id': None,  
                'title': None,
                'url': None,
                'body': None,
                'day': None,
                'time': None,
                'frequency': None
            }

            # Map the matches to the correct keys in the dictionary
            for key, value in matches:
                if key == 'c':
                    post_data['community'] = value
                elif key == 't':
                    post_data['title'] = value
                elif key == 'b':
                    post_data['body'] = value
                elif key == 'u':
                    post_data['url'] = value
                elif key == 'd':
                    post_data['day'] = value
                elif key == 'h':
                    post_data['time'] = value
                elif key == 'f':
                    post_data['frequency'] = value

            #check mandatory fields
            if post_data['community'] == None:
                lemmy.private_message.create("Hey, " + pm_username + ". In order to use this command, you will need to specify a community with the `-c` flag, i.e. `-c gaming`."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


            if post_data['title'] == None:
                lemmy.private_message.create("Hey, " + pm_username + ". In order to use this command, you will need to specify a title with the `-t` flag, i.e. `-t Weekly Thread`. You can also use the following commands in the title: \n\n"
                                            "- %d (Day - i.e. 12) \n"
                                            "- %m (Month - i.e. June) \n"
                                            "- %y (Year - i.e. 2023) \n"
                                            "- %w (Weekday - i.e. Monday) \n\n"
                                            "For example, `Gaming Thread %w %d %m %y` would give you a title of `Gaming Thread Monday 12 June 2023`."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['day'] == None:
                lemmy.private_message.create("Hey, " + pm_username + ". In order to use this command, you will need to specify a day of the week with the `-d` flag, i.e. `-d monday`, or a specific date you want the first post to be posted in YYYYMMDD format, i.e. `-d 20230612."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['time'] == None:
                lemmy.private_message.create("Hey, " + pm_username + ". In order to use this command, you will need to specify a time with the `-h` flag, i.e. `-h 07:30` Remember all times are UTC!."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if post_data['frequency'] == None:
                lemmy.private_message.create("Hey, " + pm_username + ". In order to use this command, you will need to specify a post frequency with the `-f` flag, i.e. `-f weekly`. \n\n"
                                            "You can use the following frequencies: \n"
                                            "- once (the post will only happen once) \n"
                                            "- weekly (every 7 days) \n"
                                            "- fortnightly (every 14 days) \n"
                                            "- 4weekly (every 28 days)"
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            
            if post_data['frequency'] not in ["once", "weekly", "fortnightly", "4weekly"]:
                lemmy.private_message.create("Hey, " + pm_username + ". I couldn't find a valid frequency following the -f flag. \n\n"
                                            "You can use the following frequencies: \n"
                                            "- once (the post will only happen once) \n"
                                            "- weekly (every 7 days) \n"
                                            "- fortnightly (every 14 days) \n"
                                            "- 4weekly (every 28 days)"
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue



            #check community is real
            output = lemmy.community.get(name=post_data['community'])

            if output == None:
                lemmy.private_message.create("Hey, " + pm_username + ". The community you requested can't be found. Please double check the spelling and name and try again."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            
            #check if user is moderator of community
            is_moderator = False

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == pm_sender:
                    is_moderator = True
                    break  # Stop the loop as soon as we find a matching moderator

            if not is_moderator:
                # If pm_sender is not a moderator, send a private message
                lemmy.private_message.create("Hey, " + pm_username + ". As you are not the moderator of this community, you are not able to create a scheduled post for it."
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            
            post_data['mod_id'] = pm_sender
            
            date_format = "%Y%m%d"

            try:
                parsed_date = datetime.strptime(post_data['day'], date_format)
                # Check if the date is in the past
                if parsed_date.date() < datetime.now().date():
                    lemmy.private_message.create("Hey, " + pm_username + ". The date of the post you scheduled is in the past. Unfortunately I don't have a time machine :( \n\n"
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue
                else:
                    day_type = "date"
            except ValueError:
                # If it's not a date, check if it's a day of the week
                weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                if post_data['day'].lower() in weekdays:
                    day_type = "day"
                else:
                    lemmy.private_message.create("Hey, " + pm_username + ". Sorry, I can't work out when you want your post scheduled. Please pick a day of the week or specify a date you want recurring posts to start! Remember dates should be in YYYYMMDD format. \n\n"
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                    lemmy.private_message.mark_as_read(pm_id, True)
                    continue

            # Convert the day, time, and frequency into a scheduled datetime
            if day_type == "day":
                if post_data['day'] and post_data['time']:
                    next_post_date = get_next_post_date(post_data['day'], post_data['time'], post_data['frequency'])
                    post_data['scheduled_post'] = next_post_date
                    dtype = "Day"

            if day_type == "date":
                if post_data['day'] and post_data['time']:
                    datetime_string = f"{post_data['day']} {post_data['time']}"
                    datetime_obj = datetime.strptime(datetime_string, '%Y%m%d %H:%M')
                    uk_timezone = pytz.timezone('Europe/London')
                    localized_datetime = uk_timezone.localize(datetime_obj)
                    post_data['scheduled_post'] = localized_datetime.astimezone(pytz.utc)
                    next_post_date = post_data['scheduled_post']
                    dtype = "Date (YYYYMMDD)"


            # Insert into database
            auto_post_id = add_autopost_to_db(post_data)

            #fix for optional fields for PM purposes
            if post_data['url'] == None:
                post_data['url'] = ""
            if post_data['body'] == None:
                post_data['body'] = ""

            

            
            lemmy.private_message.create("Hey, " + pm_username + ". \n\n"
                                        "The details for your scheduled post are as follows: \n\n"
                                        "- Community: " + post_data['community'] + "\n\n"
                                        "- Post Title: " + post_data['title'] + "\n"
                                        "- Post Body: " + post_data['body'] + "\n"
                                        "- Post URL: " + post_data['url'] + "\n"
                                        "- " + dtype + ": " + post_data['day'] + "\n"
                                        "- Time (UTC): " + post_data['time'] + "\n"
                                        "- Frequency: " + post_data['frequency'] + "\n"
                                        "- Your next post date is: " + str(next_post_date) + "\n\n"
                                        "- The ID for this autopost is: " + str(auto_post_id) + ". (Keep this safe as you will need it to cancel your autopost in the future, if you've set up for a repeating schedule.)"
                                        "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" ")[0] == "#autopostdelete":
            pin_id = pm_context.split(" ")[1]

            delete_conf = delete_autopost(pin_id, pm_sender)

            if delete_conf == "deleted":
                lemmy.private_message.create("Hey, " + pm_username + ". Your pinned autopost (with ID " + pin_id + ") has been successfully deleted."
                "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            
            if delete_conf == "not deleted":
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
                                                                "Please also take a look at our rules, they are in the sidebar of this instance, or you can view them [here](https://legal.lemmy.zip/docs/code_of_conduct/), or I can send these to you at any time - just send me a message with `#rules`. \n \n"
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
                                                                "- You should also add your community to the [Lemmy Community Boost project](https://boost.lemy.lol) so it is automatically shared to a bunch of other instances.\n"
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
    #url of rss feeds
    rss_urls = [
        "https://www.gameinformer.com/news.xml",
        "https://www.rockpapershotgun.com/feed/news",
        "https://www.gamingonlinux.com/article_rss.php"
    ]
    for rss_url in rss_urls:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:2]:
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
            news_query = '''SELECT article_title FROM game_news WHERE article_title=? '''
            news_match = execute_sql_query(conn, news_query, (article_title,))

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
        

def post_reports():
    
    recent_reports = lemmy.post.report_list(limit=5, unresolved_only="true")

    #define words in the report that will trigger the urgent message
    serious_words= ["csam", "illegal", "kill", "suicide"]

    if recent_reports:
        #recent_reports = lemmy.post.report_list(limit=10)
        for report in recent_reports:
            serious_flag = False  
            creator = report['creator']['name']
            creator_id = report['post_report']['creator_id']
            local_user = report['creator']['local']
            report_id = report['post_report']['id']
            report_reason = report['post_report']['reason']
            #activity pub id (i.e. home instance post url)
            ap_id = report['post']['ap_id']
            reported_content_id = report['post_report']['post_id']

            report_reason = report_reason.lower()

            for word in serious_words:
                if word in report_reason:
                    serious_flag = True
                    break              

            local_post = re.search(settings.INSTANCE, str(ap_id))

            if local_user == False:
                local_post = True

            if serious_flag:
                if not local_post:
                    report_reply = ("Thank you for submitting your report. \n\n We take each report seriously and ensure it undergoes a thorough manual review. Please note, since the content you reported is not hosted directly on Lemmy.zip," 
                                    "our ability to take action might be limited if it doesn't violate Lemmy.zip's [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/). \n" 
                                    "Responsibility for moderation in such cases typically falls to the moderators and admins of the specific local instance where the content is posted.\n\n"
                                    "However, if you believe the content in question is illegal or demands urgent attention, we urge you to reply to this message immediately with `#urgent -p -" + str(report_id) + "` (copy and paste only this text into the reply box).\n\n" 
                                    "This will alert our administration team, who will take immediate action as necessary. Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")            
                
                if local_post:
                    report_reply = ("Thank you for submitting your report. \n\n We value your effort in helping us maintain a safe and respectful community on Lemmy.zip. Every report is taken seriously and undergoes a thorough manual review by our team.\n"
                                    "We assure you that appropriate actions will be taken based on our [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/).\n\n"
                                    "In instances where you believe the content is illegal and/or requires urgent intervention (such as CSAM or a threat to life), we urge you to reply to this message immediately with `#urgent -p -" + str(report_id) + "` (copy and paste only this text into the reply box). \n\n"
                                    "This will alert our administration team who will take immediate action as necessary. Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")
                    
            if not serious_flag:
                if not local_post:
                    report_reply = ("Thank you for submitting your report. \n\n We take each report seriously and ensure it undergoes a thorough manual review. Please note, since the content you reported is not hosted directly on Lemmy.zip," 
                                    "our ability to take action might be limited if it doesn't violate Lemmy.zip's [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/). \n" 
                                    "Responsibility for moderation in such cases typically falls to the moderators and admins of the specific local instance where the content is posted.\n\n" 
                                    "Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")            
                
                if local_post:
                    report_reply = ("Thank you for submitting your report. \n\n We value your effort in helping us maintain a safe and respectful community on Lemmy.zip. Every report is taken seriously and undergoes a thorough manual review by our team.\n"
                                    "We assure you that appropriate actions will be taken based on our [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/).\n\n"
                                    "Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")

            with connect_to_reports_db() as conn:
                check_reports = '''SELECT report_id FROM post_reports WHERE report_id=?'''
                report_match = execute_sql_query(conn, check_reports, (report_id,))

                if not report_match:
                    #tables: 'post_reports', '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, post_id INT'
                    sqlite_insert_query = """INSERT INTO post_reports (report_id, reporter_id, reporter_name, report_reason, post_id) VALUES (?,?,?,?,?);"""
                    data_tuple = (report_id, creator_id, creator, report_reason, reported_content_id,)
                    execute_sql_query(conn, sqlite_insert_query, data_tuple)
            
                    lemmy.private_message.create("Hello " + creator + ",\n\n" + report_reply + "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", creator_id)

def comment_reports():
    recent_reports = lemmy.comment.report_list(limit=5, unresolved_only="true")
 

    #define words in the report that will trigger the urgent message
    serious_words= ["csam", "illegal", "kill", "suicide"]

    for report in recent_reports:
        
        serious_flag = False  
        reporter= report['creator']['name']
        reporter_id = report['creator']['id']
        creator_url = report['comment_creator']['actor_id']
        local_user = report['creator']['local']
        report_id = report['comment_report']['id']
        report_reason = report['comment_report']['reason']
        #activity pub id (i.e. home instance post url)
        ap_id = report['comment']['ap_id']
        reported_content_id = report['comment_report']['comment_id']

        report_reason = report_reason.lower()

        for word in serious_words:
            if word in report_reason:
                serious_flag = True
                break     
        
        local_post = re.search(settings.INSTANCE, str(ap_id))

        if local_user == False:
            local_post = True

        if serious_flag:
            if not local_post:
                report_reply = ("Thank you for submitting your report. \n\n We take each report seriously and ensure it undergoes a thorough manual review. Please note, since the content you reported is not hosted directly on Lemmy.zip," 
                                "our ability to take action might be limited if it doesn't violate Lemmy.zip's [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/). \n" 
                                "Responsibility for moderation in such cases typically falls to the moderators and admins of the specific local instance where the content is posted.\n\n"
                                "However, if you believe the content in question is illegal or demands urgent attention, we urge you to reply to this message immediately with `#urgent -c -" + str(report_id) + "` (copy and paste only this text into the reply box).\n\n" 
                                "This will alert our administration team, who will take immediate action as necessary. Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")            
            
            if local_post:
                report_reply = ("Thank you for submitting your report. \n\n We value your effort in helping us maintain a safe and respectful community on Lemmy.zip. Every report is taken seriously and undergoes a thorough manual review by our team.\n"
                                "We assure you that appropriate actions will be taken based on our [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/).\n\n"
                                "In instances where you believe the content is illegal and/or requires urgent intervention (such as CSAM or a threat to life), we urge you to reply to this message immediately with `#urgent -c -" + str(report_id) + "` (copy and paste only this text into the reply box). \n\n"
                                "This will alert our administration team who will take immediate action as necessary. Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")
                
        if not serious_flag:
            if not local_post:
                report_reply = ("Thank you for submitting your report. \n\n We take each report seriously and ensure it undergoes a thorough manual review. Please note, since the content you reported is not hosted directly on Lemmy.zip," 
                                "our ability to take action might be limited if it doesn't violate Lemmy.zip's [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/). \n" 
                                "Responsibility for moderation in such cases typically falls to the moderators and admins of the specific local instance where the content is posted.\n\n" 
                                "Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")            
            
            if local_post:
                report_reply = ("Thank you for submitting your report. \n\n We value your effort in helping us maintain a safe and respectful community on Lemmy.zip. Every report is taken seriously and undergoes a thorough manual review by our team.\n"
                                "We assure you that appropriate actions will be taken based on our [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/).\n\n"
                                "Your vigilance in helping maintain a safe and respectful community is greatly appreciated.")

        with connect_to_reports_db() as conn:
            check_reports = '''SELECT report_id FROM comment_reports WHERE report_id=?'''
            report_match = execute_sql_query(conn, check_reports, (report_id,))

            if not report_match:
                sqlite_insert_query = """INSERT INTO comment_reports (report_id, reporter_id, reporter_name, report_reason, comment_id) VALUES (?,?,?,?,?);"""
                data_tuple = (report_id, reporter_id, reporter, report_reason, reported_content_id,)
                execute_sql_query(conn, sqlite_insert_query, data_tuple)
        
                lemmy.private_message.create("Hello " + reporter + ",\n\n" + report_reply + "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", reporter_id)


def check_reports():
    post_reports()
    comment_reports()

def get_next_post_date(day, time, frequency):
    # Map days to integers

    day = day.lower()
    
    days = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    # Frequency mapping 
    frequency_mapping = {
        'once': 0,
        'weekly': 7,
        'fortnightly': 14,
        '4weekly': 28  # Every 4 weeks
        
    }
    
    today = datetime.now()
    today_weekday = today.weekday()
    target_weekday = days[day]

    # Calculate days until the next target day
    days_until_next = (target_weekday - today_weekday + 7) % 7
    if days_until_next == 0:
        days_until_next = 7

    # Adjust for frequency only if the next posting date is not today
    if days_until_next != 0:
        days_until_next += frequency_mapping.get(frequency, 7)

    # Combine date and time
    next_post_datetime = today + timedelta(days=days_until_next)
    post_time = datetime.strptime(time, "%H:%M").time()
    return datetime.combine(next_post_datetime.date(), post_time)

def calc_next_post_date(old_post_date, frequency):
    # Map frequency to days
    frequency_mapping = {
        'once': 0,
        'weekly': 7,
        'fortnightly': 14,
        '4weekly': 28
    }

    if frequency == 'once':
        return "delete"

    # Get the number of days to add for the given frequency
    days_to_add = frequency_mapping.get(frequency, 7)

    # Add the days to the old_post_date
    new_post_date = old_post_date + timedelta(days=days_to_add)

    return new_post_date

def check_scheduled_posts():
    #first get current time/date in UTC
    current_utc = datetime.now(timezone.utc)

    #second connect to DB and check all rows for a matching time/data parameter
    with connect_to_autopost_db() as conn:
        cursor = conn.cursor()
        query = "SELECT pin_id, scheduled_post FROM com_posts"
        cursor.execute(query)
        records = cursor.fetchall()

        one_minute = timedelta(minutes=1)

        # Process each record
        for record in records:
            record_id, stored_time_str = record
            stored_datetime = datetime.fromisoformat(stored_time_str)
            stored_datetime = stored_datetime.replace(tzinfo=timezone.utc)

            # Check if the stored time is within 1 minute past current UTC
            if current_utc - one_minute < stored_datetime <= current_utc:
                # Fetch the full row for the record_id
                full_row_query = "SELECT * FROM com_posts WHERE pin_id = ?"
                cursor.execute(full_row_query, (record_id,))
                full_row = cursor.fetchone()
                
                community_name = full_row[1]
                post_title = full_row[3]
                post_url = full_row[4]
                post_body = full_row[5]
                post_frequency = full_row[7]
                previous_post = full_row[8]

                if previous_post is not None:
                    lemmy.post.feature(int(previous_post), False, FeatureType.Community)
                
                com_details = lemmy.community.get(name=community_name)

                if com_details == None:
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (record_id,))
                    conn.commit
                    continue

                #format body string
                post_body = post_body.replace("%m", current_utc.strftime("%B")) #Month name
                post_body = post_body.replace("%d", current_utc.strftime("%d")) #Day of the month
                post_body = post_body.replace("%y", current_utc.strftime("%Y")) #Year
                post_body = post_body.replace("%w", current_utc.strftime("%A")) #Day of the week

                #format title string
                post_title = post_title.replace("%m", current_utc.strftime("%B")) #Month name
                post_title = post_title.replace("%d", current_utc.strftime("%d")) #Day of the month
                post_title = post_title.replace("%y", current_utc.strftime("%Y")) #Year
                post_title = post_title.replace("%w", current_utc.strftime("%A")) #Day of the week


                com_id = com_details['community_view']['community']['id']
                #create post
                post_output = lemmy.post.create(com_id,post_title,post_url,post_body)

                #get post ID
                previous_post = post_output['post_view']['post']['id']

                query = "UPDATE com_posts SET previous_post = ? WHERE pin_id = ?"
                cursor.execute(query, (previous_post, record_id))
                conn.commit()

                lemmy.post.feature(previous_post, True, feature_type=FeatureType.Community)

                #need to work out when to make the next post
                old_post_date = stored_datetime
                next_post_date = calc_next_post_date(old_post_date, post_frequency)
                #check for "once" posts
                if next_post_date == 'delete':
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (record_id,))
                    conn.commit
                    continue

                query = "UPDATE com_posts SET scheduled_post = ? WHERE pin_id = ?"
                cursor.execute(query, (next_post_date, record_id))
                conn.commit()

    # Close the database connection
    conn.close()


async def send_matrix_message(matrix_body):
    client = AsyncClient("https://matrix.org", "@lemmy-uptime-bot:matrix.org")

 # Use an access token to log in
    client.access_token = settings.MATRIX_API_KEY

    # Replace with the room ID or alias of the room you want to send a message to
    room_id = settings.MATRIX_ROOM_ID

    # Send a message to the room
    await client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={
            "msgtype": "m.text",
            "body": matrix_body
        }
    )

    # Logging out is not necessary when using an access token, but you might want to close the client session
    await client.close()


