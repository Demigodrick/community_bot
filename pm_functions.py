# Standard library imports
import asyncio
import logging
import os
from datetime import datetime, timedelta
import pytz
import re
import sqlite3
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import shlex

# Third-party imports
import feedparser
import requests
from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType, FeatureType

# Local imports
from config import settings
from lemmy_manager import get_lemmy_instance
import bot_strings


lemmy = get_lemmy_instance()


def pm_help(user_admin, pm_username, pm_id, pm_sender):
    greeting = f"{bot_strings.GREETING} {pm_username}. "
    commands = bot_strings.BOT_COMMANDS  # Common part for all users

    # Add admin commands if user is an admin
    if user_admin:
        commands += bot_strings.BOT_ADMIN_COMMANDS

    # Add the signoff at the end
    commands += bot_strings.PM_SIGNOFF

    # Send the message
    lemmy.private_message.create(greeting + commands, pm_sender)

    # Mark the message as read
    lemmy.private_message.mark_as_read(pm_id, True)


def pm_sub(pm_sender, status, pm_username, pm_id, broadcast_status):
    if broadcast_status(pm_sender, status) == "successful":
        message = bot_strings.UNSUB_MESSAGE if status == "unsub" else bot_strings.SUB_MESSAGE
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}\n\n{message}\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.create(
        f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.SUB_ERROR}",
        pm_sender)
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_takeover(user_admin, pm_context, pm_id, pm_username, pm_sender):
    if user_admin:
        community_name = pm_context.split("-")[1].strip()
        user_id = pm_context.split("-")[2].strip()

        if user_id == "self":
            user_id = pm_id

        community_id = lemmy.discover_community(community_name)

        logging.info(
            "Request for community %s to be transferred to %s", community_name, user_id
        )


        if community_id is None:
            lemmy.private_message.create(
                f"{bot_strings.GREETING} {pm_username}. Sorry, I can't find the community you've requested.",
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            return

        lemmy.community.add_mod_to_community(
            True, community_id=int(community_id), person_id=int(user_id))
        lemmy.private_message.create(
            f"Confirmation: {community_name} ({community_id}) has been taken over by user id {user_id}.",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return

def pm_removemod(user_admin, pm_context, pm_id, pm_username, pm_sender):
    if user_admin:
        community_name = pm_context.split("-")[1].strip()
        user_id = pm_context.split("-")[2].strip()

        if user_id == "self":
            user_id = pm_id

        community_id = lemmy.discover_community(community_name)

        logging.info(
            "Request for moderator %s to be removed from %s", user_id, community_name
        )


        if community_id is None:
            lemmy.private_message.create(
                f"{bot_strings.GREETING} {pm_username}. Sorry, I can't find the community you've requested.",
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            return

        lemmy.community.add_mod_to_community(
            False, community_id=int(community_id), person_id=int(user_id))
        lemmy.private_message.create(
            f"Confirmation: {community_name} ({community_id}) has had a moderator removed with user id {user_id}.",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return
        


def pm_vote(
        pm_context,
        pm_username,
        pm_account_age,
        pm_id,
        pm_sender,
        add_vote_to_db):
    vote_id = pm_context.split(" ")[1]
    vote_response = pm_context.split(" ")[2]

    db_response = add_vote_to_db(
        pm_username,
        vote_id,
        vote_response,
        pm_account_age)

    if db_response == "duplicate":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Oops! It looks like you've already voted on this poll. Votes can only be counted once. \n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if db_response == "notvalid":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Oops! It doesn't look like the poll you've tried to vote on exists. Please double check the vote ID and try again. \n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if db_response == "closed":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, it appears the poll you're trying to vote on is now closed. Please double check the vote ID and try again. \n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.create(
        f"{bot_strings.GREETING} {pm_username}. Your vote has been counted on the \'{db_response}\' poll. Thank you for voting! \n\n{bot_strings.PM_SIGNOFF}",
        pm_sender)
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_poll(
        user_admin,
        pm_context,
        pm_username,
        pm_id,
        pm_sender,
        create_poll):
    if user_admin:
        poll_name = pm_context.split("@")[1]
        poll_id = create_poll(poll_name, pm_username)
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Your poll has been created with ID number {poll_id}. You can now give this ID to people and they can now cast a vote using the `#vote` operator.\n\n {bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.create(
        f"{bot_strings.GREETING} {pm_username}. You need to be an instance admin in order to create a poll.\n\n {bot_strings.PM_SIGNOFF}",
        pm_sender)
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_closepoll(
        user_admin,
        pm_context,
        pm_username,
        pm_id,
        pm_sender,
        close_poll):
    if user_admin:
        poll_id = pm_context.split("@")[1]
        if close_poll(poll_id) == "closed":
            lemmy.private_message.create(
                f"{bot_strings.GREETING} {pm_username}. Your poll (ID = {poll_id}) has been closed \n\n {bot_strings.PM_SIGNOFF}",
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            return
    lemmy.private_message.create(
        f"{bot_strings.GREETING} {pm_username}. I couldn't close that poll due to an error. \n\n {bot_strings.PM_SIGNOFF}",
        pm_sender)
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_countpoll(
        user_admin,
        pm_context,
        pm_username,
        pm_id,
        pm_sender,
        count_votes):
    if user_admin:
        poll_id = pm_context.split("@")[1]
        yes_votes, no_votes = count_votes(poll_id)
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. There are {yes_votes} yes votes and {no_votes} no votes on that poll. \n\n {bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_giveaway(user_admin, pm_id, pm_context, add_giveaway_thread):
    if user_admin:
        thread_id = pm_context.split(" ")[1]
        add_giveaway_thread(thread_id)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_closegiveaway(user_admin, close_giveaway_thread, pm_context, pm_id):
    if user_admin:
        thread_id = pm_context.split(" ")[1]
        close_giveaway_thread(thread_id)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_drawgiveaway(
        user_admin,
        draw_giveaway_thread,
        pm_context,
        pm_username,
        pm_sender,
        pm_id):
    if user_admin:
        thread_id = pm_context.split(" ")[1]
        num_winners = pm_context.split(" ")[2]
        draw_status = draw_giveaway_thread(thread_id, num_winners)
        if draw_status == "min_winners":
            lemmy.private_message.create(
                f"{bot_strings.GREETING} {pm_username}. There are too few entrants to draw your giveaway with that many winners. Please reduce the amount of winners or encourage more entrants! \n\n {bot_strings.PM_SIGNOFF}",
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            return

        winners = draw_status
        winner_names = ', '.join(winners)
        comment_body = f"Congratulations to the winners of this giveaway: {winner_names}!\n\nThe winners of this giveaway have been drawn randomly by ZippyBot."
        lemmy.comment.create(int(thread_id), comment_body)
        lemmy.post.lock(int(thread_id), True)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_broadcast(user_admin, pm_context, pm_id, broadcast_message):
    if user_admin:
        message = pm_context.replace('#broadcast', "", 1)
        broadcast_message(message)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_rssdelete(pm_context, pm_sender, pm_username, pm_id, delete_rss):
    feed_id = pm_context.split(" ")[1]
    status = delete_rss(feed_id, pm_sender)

    if status == "no_exist":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, there is not an RSS feed with that ID number. Please try again.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if status == "not_mod":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, you'll need to be a mod of this community before deleting an RSS feed.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if status == "deleted":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. The RSS feed has been deleted for this community.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_welcomedelete(
        pm_context,
        pm_username,
        pm_sender,
        pm_id,
        delete_welcome):

    com_name = pm_context.split(" ")[1]
    status = delete_welcome(com_name, pm_sender)

    if status == "no_exist":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, there is not a Welcome message associated with that community.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if status == "not_mod":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, you'll need to be a mod of this community before deleting the Welcome message.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if status == "deleted":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. The Welcome message has been deleted for this community.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_comscan(pm_context, pm_username, pm_sender, pm_id, add_community_word):
    parts = pm_context.split()
    filters = {
        'words': None,
        'community': None,
        'action': None
    }

    flag = None
    for part in parts:
        if part.startswith('-'):
            flag = part
        elif flag:
            if flag == '-w':
                filters['words'] = part.split(',')
            elif flag == '-a':
                filters['action'] = part
            elif flag == '-c':
                filters['community'] = part
            flag = None

    if not filters['community']:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. You will need to specify the community with the `-c` flag for this tool to work.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if not filters['words']:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. You will need to specify words in a comma-separated list, i.e., `-w word1,word2,word3`.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if not filters['action']:
        filters['action'] = "report"

    if filters['action'] != "report" and filters['action'] != "remove":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. You've not defined a valid action to take. Please ensure you either use `-a report` or `-a remove`.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    output = lemmy.community.get(name=filters['community'])

    for moderator_info in output['moderators']:
        if moderator_info['moderator']['id'] == pm_sender:
            is_moderator = True
            break

    if not is_moderator:
        # if pm_sender is not a moderator, send a private message
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. As you are not the moderator of this community, you are not able to use this tool for it.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    word_add_result = add_community_word(
        filters['community'],
        filters['words'],
        filters['action']
    )

    if word_add_result == "added":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Your list of words has been created/updated. ZippyBot will scan for these words and action them as requested.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_welcome(pm_context, pm_username, pm_sender, pm_id, add_welcome_message):

    filters = {
        'community': None,
        'message': None
    }

    c_index = pm_context.find('-c')
    m_index = pm_context.find('-m')

    # Extract community name
    if c_index != -1 and m_index != -1:
        community_name = pm_context[c_index + 3:m_index].strip()
        filters['community'] = community_name

    # Extract message, considering everything after "-m"
    if m_index != -1:
        message = pm_context[m_index + 3:].strip(' “”"\'\n')
        filters['message'] = message

    if not filters['message']:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, you can't have a blank welcome message for a community. Please include some text, personalise the message and make it welcoming and friendly!\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    output = lemmy.community.get(name=filters['community'])

    if output is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. The community you requested can't be found. Please double check the spelling and name and try again.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    for moderator_info in output['moderators']:
        if moderator_info['moderator']['id'] == pm_sender:
            is_moderator = True
            break

    if not is_moderator:
        # if pm_sender is not a moderator, send a private message
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. As you are not the moderator of this community, you are not able to set a welcome message for it.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    welcome_message_result = add_welcome_message(
        filters['community'],
        filters['message']
    )

    if welcome_message_result == "added":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. I have successfully added the welcome message to the community. You can run this command again to change the message.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_rss(
        pm_context,
        pm_username,
        pm_sender,
        pm_id,
        add_new_feed,
        connect_to_rss_db,
        fetch_latest_posts,
        insert_new_post):
    pattern = r'-(url|url_exc|url_inc|title_inc|title_exc|c|t|new_only|ignore)\s*(?:(?:"(.*?)")|(?:“(.*?)”)|([^\s]+))?(?=\s+-|$)'

    filters = {
        'feed_url': None,
        'url_excludes_filter': None,
        'url_contains_filter': None,
        'title_excludes_filter': None,
        'title_contains_filter': None,
        'community': None,
        'tag': None
    }

    ignore_bozo_check = False
    new_only = False

    matches = re.findall(pattern, pm_context)

    for match in matches:
        flag = match[0]
        value = next((m for m in match[1:] if m), None)

        if flag == 'url':
            filters['feed_url'] = value
        elif flag == 'url_exc':
            filters['url_excludes_filter'] = value
        elif flag == 'url_inc':
            filters['url_contains_filter'] = value
        elif flag == 'title_inc':
            filters['title_contains_filter'] = value
        elif flag == 'title_exc':
            filters['title_excludes_filter']
        elif flag == 'c':
            filters['community'] = value
        elif flag == 't':
            filters['tag'] = value
        elif flag == 'new_only':
            new_only = True
        elif flag == 'ignore':
            ignore_bozo_check = True

    if not filters['feed_url']:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. You will need to include a link to an RSS feed for this to work.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if not filters['community']:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. You will need to specify the community you want the RSS feed to be posted to with `-c community_name`.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    output = lemmy.community.get(name=filters['community'])

    if output is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. The community you requested can't be found. Please double check the spelling and name and try again.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    com_name = filters['community']
    filters['community'] = lemmy.discover_community(
        filters['community'])

    # check if user is moderator of community
    is_moderator = False

    for moderator_info in output['moderators']:
        if moderator_info['moderator']['id'] == pm_sender:
            is_moderator = True
            break

    if not is_moderator:
        # if pm_sender is not a moderator, send a private message
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. As you are not the moderator of this community, you are not able to add an RSS feed to it.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    # check url is a valid rss feed
    feed_url = filters['feed_url']
    valid_rss = feedparser.parse(feed_url)
    if not ignore_bozo_check and (
            valid_rss.bozo != 0 or 'title' not in valid_rss.feed):
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. I can't find a valid RSS feed in the URL you've provided. Please double check you're linking directly to an RSS feed.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    
    add_new_feed_result = add_new_feed(
        filters['feed_url'],
        filters['url_contains_filter'],
        filters['url_excludes_filter'],
        filters['title_contains_filter'],
        filters['title_excludes_filter'],
        filters['community'],
        filters['tag']
    )

    if add_new_feed_result == "exists":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. The RSS feed you're trying to add already exists in the [{com_name}](/c/{com_name}@{settings.INSTANCE}) community.",
            pm_sender
        )
    elif add_new_feed_result is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. An error occurred while adding the RSS feed. Please try again.",
            pm_sender
        )
    else:
        feed_id = add_new_feed_result
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. I have successfully added the requested RSS feed to the [{com_name}](/c/{com_name}@{settings.INSTANCE}) community. The ID for this RSS feed is {add_new_feed_result} - please keep this safe as you'll need it if you want to delete the feed in the future.",
            pm_sender
        )
    lemmy.private_message.mark_as_read(pm_id, True)

    if new_only:
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag
                FROM feeds
                WHERE feed_url = ?
                """, (feed_url,))

            feed_details = cursor.fetchone()

        if feed_details:
            feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag = feed_details
            posts = fetch_latest_posts(
                feed_url,
                url_contains_filter,
                url_excludes_filter,
                title_contains_filter,
                title_excludes_filter)
            for post in posts:
                insert_new_post(feed_id, post)


def pm_autopost(pm_context, pm_username, pm_sender, pm_id, add_autopost_to_db, get_first_post_date):
    # define the pattern to match each qualifier and its following
    # content
    pattern = r"-(c|t|b|u|d|h|f)\s+(\"[^\"]*\"|'[^']*'|[^\"\s-][^\s-]*)"

    # find all matches
    matches = re.findall(pattern, pm_context)

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

    # map the matches to the correct keys in the dictionary
    for key, value in matches:
        # If the value is wrapped in quotes, remove the quotes
        if value.startswith('"') and value.endswith(
                '"') or value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
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

    # check mandatory fields
    if post_data['community'] is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. In order to use this command, you will need to specify a community with the `-c` flag, i.e. `-c gaming`.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if post_data['title'] is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. In order to use this command, you will need to specify a title with the `-t` flag, i.e. `-t Weekly Thread`. You can also use the following commands in the title: \n\n"
            "- %d (Day - i.e. 12) \n"
            "- %m (Month - i.e. June) \n"
            "- %y (Year - i.e. 2023) \n"
            "- %w (Weekday - i.e. Monday) \n\n"
            "For example, `Gaming Thread %w %d %m %y` would give you a title of `Gaming Thread Monday 12 June 2023`.\n\n"
            f"{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if post_data['day'] is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. In order to use this command, you will need to specify a day of the week with the `-d` flag, i.e. `-d monday`, or a specific date you want the first post to be posted in YYYYMMDD format, i.e. `-d 20230612`.\n\n"
            f"{bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if post_data['time'] is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. In order to use this command, you will need to specify a time with the `-h` flag, i.e. `-h 07:30`. Remember all times are UTC!.\n\n"
            f"{bot_strings.PM_SIGNOFF}", pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if post_data['frequency'] is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. In order to use this command, you will need to specify a post frequency with the `-f` flag, i.e. `-f weekly`. \n\n"
            f"You can use the following frequencies: \n"
            f"- once (the post will only happen once) \n"
            f"- weekly (every 7 days) \n"
            f"- fortnightly (every 14 days) \n"
            f"- 4weekly (every 28 days) \n"
            f"- monthly (once a month)\n\n"
            f"{bot_strings.PM_SIGNOFF}", pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if post_data['frequency'] not in [
            "once", "weekly", "fortnightly", "4weekly", "monthly"]:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. I couldn't find a valid frequency following the -f flag. \n\n"
            f"You can use the following frequencies: \n"
            f"- once (the post will only happen once) \n"
            f"- weekly (every 7 days) \n"
            f"- fortnightly (every 14 days) \n"
            f"- 4weekly (every 28 days) \n"
            f"- monthly (once a month)\n\n"
            f"{bot_strings.PM_SIGNOFF}", pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    # check community is real
    output = lemmy.community.get(name=post_data['community'])

    if output is None:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. The community you requested can't be found. Please double check the spelling and name and try again.\n\n"
            f"{bot_strings.PM_SIGNOFF}", pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    # check if user is moderator of community
    is_moderator = False

    for moderator_info in output['moderators']:
        if moderator_info['moderator']['id'] == pm_sender:
            is_moderator = True
            break  # stop the loop as soon as we find a matching moderator

    if not is_moderator:
        # if pm_sender is not a moderator, send a private message
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. As you are not the moderator of this community, you are not able to create a scheduled post for it.\n\n"
            f"{bot_strings.PM_SIGNOFF}", pm_sender)

        lemmy.private_message.mark_as_read(pm_id, True)
        return

    post_data['mod_id'] = pm_sender

    date_format = "%Y%m%d"

    try:
        parsed_date = datetime.strptime(post_data['day'], date_format)
        # check if the date is in the past
        if parsed_date.date() < datetime.now().date():
            lemmy.private_message.create(
                f"{bot_strings.GREETING} {pm_username}. The date of the post you scheduled is in the past. Unfortunately, I don't have a time machine :( \n\n{bot_strings.PM_SIGNOFF}",
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            return
        else:
            day_type = "date"
    except ValueError:
        # if it's not a date, check if it's a day of the week
        weekdays = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday"]
        if post_data['day'].lower() in weekdays:
            day_type = "day"
        else:
            lemmy.private_message.create(
                f"{bot_strings.GREETING} {pm_username}. Sorry, I can't work out when you want your post scheduled. Please pick a day of the week or specify a date you want recurring posts to start! Remember dates should be in YYYYMMDD format. \n\n{bot_strings.PM_SIGNOFF}",
                pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            return

    # Convert the day, time, and frequency into a scheduled datetime
    if day_type == "day":
        if post_data['day'] and post_data['time']:
            next_post_date = get_first_post_date(
                post_data['day'], post_data['time'], post_data['frequency'])
            post_data['scheduled_post'] = next_post_date
            dtype = "Day"

    if day_type == "date":
        if post_data['day'] and post_data['time']:
            datetime_string = f"{post_data['day']} {post_data['time']}"
            datetime_obj = datetime.strptime(
                datetime_string, '%Y%m%d %H:%M')
            uk_timezone = pytz.timezone('UTC')
            localized_datetime = uk_timezone.localize(datetime_obj)
            post_data['scheduled_post'] = localized_datetime.astimezone(
                pytz.utc)
            next_post_date = post_data['scheduled_post']
            dtype = "Date (YYYYMMDD)"

    # Insert into database
    auto_post_id = add_autopost_to_db(post_data)

    # fix for optional fields for PM purposes
    if post_data['url'] is None:
        post_data['url'] = ""
    if post_data['body'] is None:
        post_data['body'] = ""

    lemmy.private_message.create(
        f"{bot_strings.GREETING} {pm_username}. \n\n"
        f"The details for your scheduled post are as follows: \n\n"
        f"- Community: {post_data['community']}\n\n"
        f"- Post Title: {post_data['title']}\n"
        f"- Post Body: {post_data['body']}\n"
        f"- Post URL: {post_data['url']}\n"
        f"- {dtype}: {post_data['day']}\n"
        f"- Time (UTC): {post_data['time']}\n"
        f"- Frequency: {post_data['frequency']}\n"
        f"- Your next post date is: {next_post_date}\n\n"
        f"- The ID for this autopost is: {auto_post_id}. (Keep this safe as you will need it to cancel your autopost in the future, if you've set up for a repeating schedule.)\n\n"
        f"{bot_strings.PM_SIGNOFF}", pm_sender)
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_autopostdelete(
        pm_context,
        delete_autopost,
        pm_username,
        pm_sender,
        pm_id):
    
    split_context = pm_context.split(" ")
    pin_id = split_context[1]
    del_post = len(split_context) >= 3 and split_context[2] != ""

    delete_conf = delete_autopost(pin_id, pm_sender, del_post)

    if delete_conf == "deleted":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Your pinned autopost (with ID {pin_id}) has been successfully deleted.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if delete_conf == "not deleted":
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if delete_conf == "no id":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. A scheduled post with this ID does not exist.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    if delete_conf == "not mod":
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. As you are not the moderator of this community, you are not able to delete a scheduled post for it.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_purgevotes(user_admin, pm_id, check_dbs):
    if user_admin:
        if os.path.exists('resources/vote.db'):
            os.remove('resources/vote.db')
            check_dbs()
            lemmy.private_message.mark_as_read(pm_id, True)
            return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_purgeadminactions(user_admin, pm_id, check_dbs):
    if user_admin:
        if os.path.exists('resources/mod_actions.db'):
            os.remove('resources/mod_actions.db')
            check_dbs()
            lemmy.private_message.mark_as_read(pm_id, True)
            return
    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_purgerss(user_admin, pm_id, check_dbs):
    if user_admin:
        if os.path.exists('resources/rss.db'):
            os.remove('resources/rss.db')
            check_dbs()
            lemmy.private_message.mark_as_read(pm_id, True)
            return
    lemmy.private_message.mark_as_read(pm_id, True)
    return

def pm_purgegiveaway(user_admin, pm_id, check_dbs):
    if user_admin:
        if os.path.exists('resources/giveaway.db'):
            os.remove('resources/giveaway.db')
            check_dbs()
            lemmy.private_message.mark_as_read(pm_id, True)
            return
    lemmy.private_message.mark_as_read(pm_id, True)
    return

def pm_reject(pm_context, pm_sender, pm_username, pm_id, reject_user):
    parts = pm_context.split("#")
    if len(parts) > 1 and parts[1].strip() == "reject":
        if pm_sender == 9532930:
            user = parts[2].strip()
            rejection = parts[3].strip()
            #added in lemmy 0.19.11
            reject_user(user, rejection)
            lemmy.private_message.mark_as_read(pm_id, True)
            return
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, you can't use this command.\n \n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return


def pm_ban(user_admin, pm_sender, pm_context, pm_id, ban_email, send_matrix_message):
    if user_admin or pm_sender == 9532930:
        person_id = pm_context.split(" ")[1]
        lemmy.private_message.mark_as_read(pm_id, True)

        ban_result = ban_email(person_id)

        banned_user = lemmy.user.get(person_id)
        if banned_user:
            banned_username = banned_user['person_view']['person']['name']

        if ban_result == "notfound":
            matrix_body = f"The ban email has failed as the user ID couldn't be found ({person_id}). Make sure you're using the public ID (can be found in the URL when sending a PM)."
            asyncio.run(send_matrix_message(matrix_body))
        elif ban_result == "sent":
            matrix_body = f"The ban email for id {banned_username}({person_id}) was sent. Modlog here: https://lemmy.zip/modlog?page=1&actionType=ModBan&userId={person_id}."
            asyncio.run(send_matrix_message(matrix_body))
        else:
            # Handles any other errors from ban_email
            matrix_body = f"There was an error sending the ban email for id {person_id}. Please check Zippy's logs!"
            asyncio.run(send_matrix_message(matrix_body))

        lemmy.private_message.mark_as_read(pm_id, True)
        return

    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_warn(
        user_admin,
        pm_context,
        pm_username,
        pm_id,
        pm_sender,
        ordinal,
        get_warning_count,
        send_matrix_message,
        log_warning):
    if user_admin:
        parts = pm_context.split("#")
        if len(parts) > 1 and parts[1].strip() == "warn":
            if len(parts) < 4:
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. Your command is incomplete. Please provide a valid user ID and warning message.\n\n{bot_strings.PM_SIGNOFF}",
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                return

            person_id = int(parts[2].strip())
            warn_message = parts[3].strip()

            try:
                person_id = int(parts[2].strip())
                if person_id <= 0:
                    raise ValueError(
                        "User ID must be a positive integer.")
            except ValueError:
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. The provided user ID is invalid. Please provide a valid positive numeric user ID.\n\n{bot_strings.PM_SIGNOFF}",
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                return

            try:
                warned_user = lemmy.user.get(person_id)
            except Exception as e:
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. Failed to retrieve user information: {str(e)}\n\n{bot_strings.PM_SIGNOFF}",
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                return

            if warned_user:
                warned_username = warned_user['person_view']['person']['name']
            else:
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. Sorry, I could not find the required user by their user ID to issue a warning. Please double-check and try again. \n \n{bot_strings.PM_SIGNOFF}",
                    pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                return

            try:
                log_warning(person_id, warn_message, pm_username)
            except ValueError as e:
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. Failed to log the warning: {str(e)}\n\n{bot_strings.PM_SIGNOFF}",
                    pm_sender)

            warning_count = ordinal(get_warning_count(person_id))

            lemmy.private_message.create(
                f"Hello, {warned_username}. This is an official warning from the Lemmy.zip Admin Team. \n\n >{warn_message} \n\n *This is your {warning_count} warning.* \n\n --- \n\n This message cannot be replied to. If you wish to dispute this warning, please reach out to any member of the Admin team.",
                int(person_id))
            lemmy.private_message.mark_as_read(pm_id, True)
            matrix_body = f"A warning has been issued by {pm_username} for user {warned_username} (User ID: {person_id}): `{warn_message}`. This is the {warning_count} warning for this user. This has been sent successfully."
            asyncio.run(send_matrix_message(matrix_body))
            return

    lemmy.private_message.mark_as_read(pm_id, True)
    return


def pm_lock(user_admin, pm_context, pm_username, pm_id, send_matrix_message):
    if user_admin:
        parts = pm_context.split("#")
        if len(parts) > 1 and parts[1].strip() == "lock":
            thread_id = parts[2].strip()
            warn_message = parts[3].strip() if len(parts) > 3 else None

            output = lemmy.post.get(int(thread_id))

            if output['post_view']['post']['local']:
                lemmy.post.lock(int(thread_id), True)

                if warn_message:
                    lemmy.comment.create(int(thread_id), warn_message)
                    time.sleep(2)  # in case of delay in posting?
                    get_comment = lemmy.comment.list(
                        post_id=int(thread_id))
                    latest_comment = max(
                        get_comment,
                        key=lambda x: x['comment']['id'],
                        default=None)['comment']['id']
                    lemmy.comment.distinguish(latest_comment, True)

                else:
                    lemmy.comment.create(
                        int(thread_id), bot_strings.THREAD_LOCK_MESSAGE)
                    time.sleep(2)  # in case of delay in posting?
                    get_comment = lemmy.comment.list(
                        post_id=int(thread_id))
                    latest_comment = max(
                        get_comment,
                        key=lambda x: x['comment']['id'],
                        default=None)['comment']['id']
                    lemmy.comment.distinguish(latest_comment, True)

                matrix_body = f"Thread locked by {pm_username}. Post: https://lemmy.zip/post/{thread_id} -> Comment: https://lemmy.zip/comment/{latest_comment}."
                asyncio.run(send_matrix_message(matrix_body))

                lemmy.private_message.mark_as_read(pm_id, True)
                return

    lemmy.private_message.mark_as_read(pm_id, True)
    return

def pm_tagenforcer(pm_username, pm_context, pm_sender, pm_id, store_enforcement):
    # Normalize quotes to avoid issues with special characters
    command = pm_context.replace("“", '"').replace("”", '"')
    tokens = shlex.split(command)
    
    lemmy.private_message.mark_as_read(pm_id, True)

    # Check for a minimum number of tokens to form a valid command
    if len(tokens) < 4:
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. Sorry, it doesn't look like your command was formatted correctly. Please try again! \n\n {bot_strings.PM_SIGNOFF}",
            pm_sender
        )
        lemmy.private_message.mark_as_read(pm_id, True)
        return

    # Parse the command tokens
    action = tokens[0]  # e.g., '#tagenforcer'
    community = tokens[1]  # e.g., 'test'
    raw_tags = tokens[2]  # e.g., '[Article],[News]'
    tags = raw_tags.strip('{}').split(',')  # Clean up tags

    steps = []
    index = 3  # Start parsing from after community and tags
    order = 0
    next_action_due = datetime.utcnow()

    while index < len(tokens):
        current_token = tokens[index]

        if current_token == ">":
            # Skip over '>' token, which just separates actions
            index += 1
            continue

        elif current_token == "warn":
            # Handle the warn action
            duration = None
            message = None

            # Check if there's a duration after "warn"
            if index + 1 < len(tokens) and tokens[index + 1].endswith('h'):
                duration = tokens[index + 1]  # e.g., '1h'
                index += 1  # Move past the duration token

            # Check if there's a message after "warn"
            message_tokens = []
            index += 1  # Move past "warn" itself
            while index < len(tokens) and not tokens[index].startswith('>') and tokens[index] not in ['wait', 'remove']:
                message_tokens.append(tokens[index])
                index += 1  # Move past the message token
            
            message = ' '.join(message_tokens).strip('""')  # Join tokens for message and strip quotes
            message = re.sub(r'\\n', '\n', message)  # Convert escaped newlines into actual newlines

            # Validate that a message was actually provided
            if not message.strip():  # Check for empty or whitespace-only messages
                logging.info("No message found after warn action - rejecting")
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. Sorry, it doesn't look like your command was formatted correctly. Your warn command is missing the message required to warn the user! Please try again! \n\n {bot_strings.PM_SIGNOFF}",
                    pm_sender
                )
                return

            steps.append({
                "order": order,
                "action": "warn",
                "duration": duration,
                "message": message
            })
            order += 1


        elif current_token == "wait":
            # Ensure there is a next token and it follows the expected format (e.g., "24h")
            if index + 1 < len(tokens) and re.fullmatch(r"\d+h", tokens[index + 1]):
                duration = int(tokens[index + 1][:-1])  # Convert "24h" -> 24
                next_action_due += timedelta(hours=duration)
                index += 1  # Move past duration
            else:
                lemmy.private_message.create(
                    f"{bot_strings.GREETING} {pm_username}. Sorry, it doesn't look like your command was formatted correctly. Your 'wait' command is missing a valid time format (e.g., 24h). Please try again!\n\n{bot_strings.PM_SIGNOFF}",
                    pm_sender
                )
                return  # Stop execution if invalid

            steps.append({
                "order": order,
                "action": "wait",
                "duration": duration,
                "message": None
            })
            order += 1
            index += 1  # Move past duration

        elif current_token == "remove":
            # Handle the remove action
            steps.append({
                "order": order,
                "action": "remove",
                "duration": None,
                "message": None
            })
            order += 1

        index += 1  # Move to the next token

    # Check user is a mod in the community
    output = lemmy.community.get(name=community)
    for moderator_info in output['moderators']:
        if moderator_info['moderator']['id'] == pm_sender:
            is_moderator = True
            break
        
    if not is_moderator:
        # if pm_sender is not a moderator, send a private message
        lemmy.private_message.create(
            f"{bot_strings.GREETING} {pm_username}. As you are not the moderator of this community, you are not able to use this tool for it.\n\n{bot_strings.PM_SIGNOFF}",
            pm_sender)
        lemmy.private_message.mark_as_read(pm_id, True)
        return
      
    store_enforcement(community, tags, steps)
    logging.info(f"New tags added to {community} community")
    
def pm_hide(user_admin, pm_context, pm_sender, pm_id, pm_username, send_matrix_message):
    lemmy.private_message.mark_as_read(pm_id, True)
    parts = pm_context.split("#")
    if len(parts) > 1 and parts[1].strip() == "hide":
        community_id = parts[2].strip()
        
        if user_admin:
            if community_id:
                com_details = lemmy.community.get(id=community_id)
                com_name = com_details['community_view']['community']['name']
            
                lemmy.community.hide(hidden=True, community_id=int(community_id))
                logging.info(f"Community {com_name} hidden from All")
                
                matrix_body = f"{pm_username} has hidden community {community_id} from the All feed."
                asyncio.run(send_matrix_message(matrix_body))
                
                return
        return   
            
def pm_spam_add(user_admin, pm_context, pm_sender, pm_id, pm_username, add_pm_spam_phrase):
    lemmy.private_message.mark_as_read(pm_id, True)
    parts = pm_context.split("#")
    if len(parts) > 1 and parts[1].strip() == "spam_add":
        spam_phrase = parts[2].strip()
        if user_admin:
            add_pm_spam_phrase(spam_phrase)

def pm_notunderstood(pm_username, pm_sender, pm_id):
    lemmy.private_message.create(
        f"{bot_strings.GREETING} {pm_username}. Sorry, I did not understand your request. Please try again or use `#help` for a list of commands. \n \n{bot_strings.PM_SIGNOFF}",
        pm_sender
    )
    lemmy.private_message.mark_as_read(pm_id, True)