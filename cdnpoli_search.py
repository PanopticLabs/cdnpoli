#!/usr/bin/env python
import os, sys, tweepy, textblob, json, re, time, requests, urllib, subprocess
from textblob import TextBlob as tb
from datetime import date, datetime, timedelta
from tweepy import OAuthHandler
from tweepy import Stream
from tweepy.streaming import StreamListener

#################################################################################
#Get relative path###############################################################
#################################################################################
script_path = os.path.abspath(__file__)
script_dir = os.path.split(script_path)[0]

#################################################################################
#Retrieve search terms###########################################################
#################################################################################
with open(os.path.join(script_dir, 'terms.json')) as json_terms:
    terms = json.load(json_terms)

#################################################################################
#Retrieve search values##########################################################
#################################################################################
with open(os.path.join(script_dir, 'search.json')) as json_search:
    search = json.load(json_search)

#################################################################################
#Retrieve authentication variables###############################################
#################################################################################
with open(os.path.join(script_dir, 'cred.json')) as json_cred:
    cred = json.load(json_cred)

#################################################################################
#Setup Panoptic API##############################################################
#################################################################################
panoptic_token = cred['panoptic_token']
panoptic_url = 'https://api.panoptic.io/cdnpoli/'
#panoptic_url = 'http://localhost/panoptic.io/api/cdnpoli/'

#################################################################################
#Setup Twitter API###############################################################
#################################################################################
consumer_key = cred['consumer_key']
consumer_secret = cred['consumer_secret']
access_token = cred['access_token']
access_secret = cred['access_secret']
#################################################################################
#################################################################################
#################################################################################

hashtags = []
def getHashtags():
    default_list = terms['hashtags']
    return default_list

def getAccounts():
    default_list = terms['accounts']
    return default_list

def getQuery():
    hashtags = getHashtags()
    accounts = getAccounts()
    combined_list = list(set(hashtags + accounts))
    return combined_list

def buildQueryStrings():
    query_strings = []
    query_array = getQuery()
    total = len(query_array)
    ranges = int(total/10)

    for i in range(0, ranges):
        start = i*10
        end = start+10
        slice = query_array[start:end]
        query_string = ''
        first = True
        for term in slice:
            if not first:
                query_string += ' OR '
            query_string += term
            first = False
        query_strings.append(query_string)

    #Remainder
    start = ranges*10
    end = len(query_array)
    slice = query_array[start:end]
    query_string = ''
    first = True
    for term in slice:
        if not first:
            query_string += ' OR '
        query_string += term
        first = False
    query_strings.append(query_string)


    return query_strings

def strip_non_ascii(string):
    ''' Returns the string without non ASCII characters'''
    stripped = (c for c in string if 0 < ord(c) < 127)
    return ''.join(stripped)


def processTweet(tweet):
    #print(json.dumps(tweet, indent=4, separators=(',', ': ')))
    try:
        user = tweet['user']
    except:
        try:
            user = tweet.author
        except:
            print('No user!')
            return False
    #Check if user is in our spam list
    try:
        result = requests.get(panoptic_url + 'spammers?data=twitter&name=' + user['screen_name']).json()['data']
    except:
        print('Cannot retrieve spammer data')
        return False
    #If user is not in spam list, continue
    if not result:
        screen_name = user['screen_name']
        name = strip_non_ascii(user['name'])
        description = strip_non_ascii(user['description']) if user['description'] else ''
        location = user['location'] if user['location'] else ''
        timezone = user['time_zone'] if user['time_zone'] else ''
        followers = user['followers_count'] if user['followers_count'] else 0
        friends = user['friends_count'] if user['friends_count'] else 0

        status_link = 'https://twitter.com/' + screen_name + '/status/' + tweet['id_str']
        user_id = requests.post(panoptic_url+'user', data={'twitterid' : user['id'], 'name' : name, 'screenname' : screen_name, 'description' : description, 'location' : location, 'timezone' : timezone, 'followers' : followers, 'friends' : friends, 'token' : panoptic_token, 'data' : 'twitter'}).json()['data']
        if(tweet['text'].startswith('RT ') is False): #Remove any retweets
            #Check for tweet
            result = requests.get(panoptic_url+'tweet?tweetid='+tweet['id_str']).json()['data']
            if not result:
                if(tweet['truncated']):
                    try:
                        text = tweet['full_text']
                    except:
                        text = tweet['text']
                else:
                    text = tweet['text']

                #print(json.dumps(user['name'], indent=4, separators=(',', ': ')))
                print(json.dumps(user['screen_name'], indent=4, separators=(',', ': ')))
                print(json.dumps(text, indent=4, separators=(',', ': ')))
                #print('')

                analysis = tb(text)
                sentiment = analysis.sentiment.polarity
                #print(sentiment)
                #Get time
                created_at = time.strptime(tweet['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
                unix = time.strftime('%s', created_at)
                #Add tweet
                favorites = tweet['favorite_count'] if tweet['favorite_count'] else 0
                retweets = tweet['retweet_count'] if tweet['retweet_count'] else 0
                try:
                    quotes = tweet['quote_count'] if tweet['quote_count'] else 0
                except:
                    quotes = 0
                try:
                    tweet_id = requests.post(panoptic_url+'tweet', data={'statusid' : tweet['id'], 'userid' : user_id, 'twitterid' : user['id'], 'tweet' : strip_non_ascii(text), 'favorites' : favorites, 'retweets' : retweets, 'quotes' : quotes, 'sentiment' : sentiment, 'unix' : unix, 'token' : panoptic_token}).json()['data']
                except:
                    print('Posting tweet failed')
                    return False
                #If quote, add connection, process quote
                if(tweet['is_quote_status']):
                    try:
                        requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : tweet['quoted_status']['user']['id'], 'screenname' : tweet['quoted_status']['user']['screen_name'], 'name' : tweet['quoted_status']['user']['name'], 'tweetid' : tweet_id, 'action' : 'quote', 'token' : panoptic_token, 'data' : 'twitter'})
                        processTweet(tweet['quoted_status'])
                    except:
                        pass
                #Add connections
                if tweet['entities']['user_mentions']:
                    for entity in tweet['entities']['user_mentions']:
                        if(tweet['in_reply_to_user_id'] == entity['id']):
                            requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : entity['id'], 'screenname' : entity['screen_name'], 'name' : entity['name'], 'tweetid' : tweet_id, 'replyid' : tweet['in_reply_to_status_id'], 'action' : 'reply', 'token' : panoptic_token, 'data' : 'twitter'})
                        else:
                            requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : entity['id'], 'screenname' : entity['screen_name'], 'name' : entity['name'], 'tweetid' : tweet_id, 'action' : 'at', 'token' : panoptic_token, 'data' : 'twitter'})

                #Check for new words
                pattern = r'(?:^|\s)(\#[^\W\d_]+)'
                search = re.findall(pattern, strip_non_ascii(text))
                search = [x.lower() for x in search]
                newwords = list(set(search) - set(hashtags))
                #Add the new words to our keyword list
                #if (len(keywords) + len(newwords)) < 500:
                if newwords:
                    print(newwords)
                    for newword in newwords:
                        requests.post(panoptic_url + 'hashtag', data={'tag' : newword, 'token' : panoptic_token})
                        hashtags.append(newword)
                #Get current date to check against the database and add to each row
                datetime = time.strftime('%Y-%m-%d %H:%M:00', created_at)

                topics = []
                t = tweet['text'].lower()
                for tag in hashtags:
                    if tag in t.split():
                        topics.append(tag)
                        #Post mention to api
                        requests.post(panoptic_url + 'mention', data={'datetime' : datetime, 'topic' : tag, 'sentiment' : sentiment, 'token' : panoptic_token, 'data' : 'twitter'})
                        #Post connection
                        requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'hashtag' : tag, 'tweetid' : tweet_id, 'action' : 'mention', 'token' : panoptic_token, 'data' : 'twitter'})

            else:
                tweet_id = result['tweetID']
                #Update favorite, retweet, quote counts
                requests.update(panoptic_url+'tweet', data={'tweetid' : tweet_id, 'favorites' : tweet['favorite_count'], 'retweets' : tweet['retweet_count'], 'quotes' : tweet['quote_count'], 'token' : panoptic_token})

            return True


        #if tweet is a retweet
        else:
            try:
                #print('RETWEET')
                #print(json.dumps(tweet['retweeted_status'], indent=4, separators=(',', ': ')))
                result = requests.get(panoptic_url+'tweet?tweetid='+tweet['retweeted_status']['id_str']).json()['data']
                text = tweet['retweeted_status']['text']
                if not result:
                    analysis = tb(text)
                    sentiment = analysis.sentiment.polarity
                    #print(sentiment)
                    #Get time
                    created_at = time.strptime(tweet['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
                    unix = time.strftime('%s', created_at)

                    #Add tweet
                    tweet_id = requests.post(panoptic_url+'tweet', data={'statusid' : tweet['retweeted_status']['id'], 'userid' : user_id, 'twitterid' : tweet['retweeted_status']['user']['id'], 'tweet' : strip_non_ascii(text), 'favorites' : tweet['retweeted_status']['favorite_count'], 'retweets' : tweet['retweeted_status']['retweet_count'], 'quotes' : tweet['retweeted_status']['quote_count'], 'sentiment' : sentiment, 'unix' : unix, 'token' : panoptic_token}).json()['data']
                else:
                    tweet_id = results['tweetID']
                    sentiment = results['sentiment']
                    requests.update(panoptic_url+'tweet', data={'tweetid' : tweet_id, 'favorites' : tweet['retweeted_status']['favorite_count'], 'retweets' : tweet['retweeted_status']['retweet_count'], 'quotes' : tweet['retweeted_status']['quote_count'], 'token' : panoptic_token})

                requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : tweet['retweeted_status']['user']['id'], 'screenname' : tweet['retweeted_status']['user']['screen_name'], 'name' : tweet['retweeted_status']['user']['name'], 'tweetid' : tweet_id, 'action' : 'retweet', 'token' : panoptic_token, 'data' : 'twitter'})

                t = text.lower()
                for tag in hashtags:
                    if tag in t.split():
                        #print(json.dumps(text, indent=4, separators=(',', ': ')))
                        #Post mention to api
                        requests.post(panoptic_url + 'mention', data={'datetime' : datetime, 'topic' : tag, 'sentiment' : sentiment, 'token' : panoptic_token, 'data' : 'twitter'})
                        #Post connection
                        requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'hashtag' : tag, 'tweetid' : tweet_id, 'action' : 'mention', 'token' : panoptic_token, 'data' : 'twitter'})
                #print('END')
            except:
                pass

    return True


auth = OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_secret)

queries = buildQueryStrings()
#query = getQuery()
#startdate = '2019-09-19'
#num_days = 7
startdate = search['date']
num_days = search['days']
print(startdate)
print(num_days)

startdt = datetime.strptime(startdate, '%Y-%m-%d')

api = tweepy.API(auth, wait_on_rate_limit=True)
#result = api.search(query)
for i in range(0, num_days):
    currentdt = startdt + timedelta(days=i)
    currentdate = datetime.strftime(currentdt, '%Y-%m-%d')
    for query in queries:
        print('Query: ' + query)
        for status in tweepy.Cursor(api.search, q=query, until=currentdate).items():
            processTweet(status._json)
    new_days = num_days - i
    #Save to json file
    new_object = {"date" : currentdate, "days" : new_days}
    with open(os.path.join(script_dir, 'search.json'), 'w') as search_file:
        json.dump(new_object, search_file, indent=4)
