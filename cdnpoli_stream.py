#!/usr/bin/env python
import os, sys, tweepy, textblob, json, re, time, requests, urllib, subprocess
from textblob import TextBlob as tb
from datetime import date, timedelta
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

def notify_node(array):
    data = json.dumps(array)
    url = 'http://165.227.32.248:5000/'
    headers = {'Content-Type': 'application/json', 'Content-Length' : str(len(data))}
    res = requests.post(url, data=data, headers=headers)

def contains_word(s, w):
    s = s.lower()
    w = w.lower()
    return (' ' + w + ' ') in (' ' + s + ' ')

def strip_non_ascii(string):
    ''' Returns the string without non ASCII characters'''
    stripped = (c for c in string if 0 < ord(c) < 127)
    return ''.join(stripped)

def remove_values_from_list(the_list, val):
   return [value for value in the_list if value != val]

def startStream():
    try:
        twitter_stream = Stream(auth, MyListener())
        twitter_stream.filter(track=query)
    #except IncompleteRead:
        # Oh well, reconnect and keep trucking
        #continue
    except Exception as e:
        print(e)
        pass

def processData(data):
    tweet = json.loads(data)
    #print(json.dumps(tweet, indent=4, separators=(',', ': ')))
    try:
        user = tweet['user']
    except:
        print('No user!')
        return False

    #Check if user is in our spam list
    result = requests.get(panoptic_url + 'spammers?data=twitter&name=' + user['screen_name']).json()['data']
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
                        text = tweet['extended_tweet']['full_text']
                        entities = tweet['extended_tweet']['entities']
                    except:
                        text = tweet['text']
                        entities = tweet['entities']
                else:
                    text = tweet['text']
                    entities = tweet['entities']

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
                datetime = time.strftime('%Y-%m-%d %H:%M:00', created_at)
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
                if entities['user_mentions']:
                    for entity in entities['user_mentions']:
                        if(tweet['in_reply_to_user_id'] == entity['id']):
                            requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : entity['id'], 'screenname' : entity['screen_name'], 'name' : entity['name'], 'tweetid' : tweet_id, 'replyid' : tweet['in_reply_to_status_id'], 'action' : 'reply', 'token' : panoptic_token, 'data' : 'twitter'})
                        else:
                            requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : entity['id'], 'screenname' : entity['screen_name'], 'name' : entity['name'], 'tweetid' : tweet_id, 'action' : 'at', 'token' : panoptic_token, 'data' : 'twitter'})

                topics = []
                if entities['hashtags']:
                    for entity in entities['hashtags']:
                        tag = '#'+entity['text']
                        if tag not in hashtags:
                            requests.post(panoptic_url + 'hashtag', data={'topic' : entity['text'], 'token' : panoptic_token})
                        #Post mention to api
                        requests.post(panoptic_url + 'mention', data={'datetime' : datetime, 'topic' : entity['text'].lower(), 'sentiment' : sentiment, 'token' : panoptic_token, 'data' : 'twitter'})
                        #Post connection
                        requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'hashtag' : entity['text'].lower(), 'tweetid' : tweet_id, 'action' : 'mention', 'token' : panoptic_token, 'data' : 'twitter'})
                        topics.append(entity['text'])
                        
                tweetObj = {'service' : 'cdnpoli', 'name' : user['name'], 'screen_name'  : user['screen_name'], 'pic' : user['profile_image_url'], 'tweet' : text.encode("utf-8"), 'link' : status_link, 'rt_count' : '0', 'fav_count' : '0', 'topics' : topics}

                if 'media' in entities:
                    tweetMedia = tweet['entities']['media'][0]['media_url_https']
                    #print(tweet['entities']['media'][0]['media_url_https'])
                    tweetObj['media'] = tweetMedia
                notify_node(tweetObj)
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
                if(tweet['retweeted_status']['truncated']):
                    try:
                        text = tweet['retweeted_status']['extended_tweet']['full_text']
                        entities = tweet['retweeted_status']['extended_tweet']['entities']
                    except:
                        text = tweet['retweeted_status']['text']
                        entities = tweet['retweeted_status']['entities']
                else:
                    text = tweet['retweeted_status']['text']
                    entities = tweet['retweeted_status']['entities']

                result = requests.get(panoptic_url+'tweet?tweetid='+tweet['retweeted_status']['id_str']).json()['data']
                if not result:
                    analysis = tb(text)
                    sentiment = analysis.sentiment.polarity
                    #print(sentiment)
                    #Get time
                    created_at = time.strptime(tweet['created_at'], "%a %b %d %H:%M:%S +0000 %Y")
                    unix = time.strftime('%s', created_at)
                    datetime = time.strftime('%Y-%m-%d %H:%M:00', created_at)

                    #Add tweet
                    tweet_id = requests.post(panoptic_url+'tweet', data={'statusid' : tweet['retweeted_status']['id'], 'userid' : user_id, 'twitterid' : tweet['retweeted_status']['user']['id'], 'tweet' : strip_non_ascii(text), 'favorites' : tweet['retweeted_status']['favorite_count'], 'retweets' : tweet['retweeted_status']['retweet_count'], 'quotes' : tweet['retweeted_status']['quote_count'], 'sentiment' : sentiment, 'unix' : unix, 'token' : panoptic_token}).json()['data']
                else:
                    tweet_id = results['tweetID']
                    sentiment = results['sentiment']
                    requests.update(panoptic_url+'tweet', data={'tweetid' : tweet_id, 'favorites' : tweet['retweeted_status']['favorite_count'], 'retweets' : tweet['retweeted_status']['retweet_count'], 'quotes' : tweet['retweeted_status']['quote_count'], 'token' : panoptic_token})

                requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'twitterid' : tweet['retweeted_status']['user']['id'], 'screenname' : tweet['retweeted_status']['user']['screen_name'], 'name' : tweet['retweeted_status']['user']['name'], 'tweetid' : tweet_id, 'action' : 'retweet', 'token' : panoptic_token, 'data' : 'twitter'})

                topics = []
                if entities['hashtags']:
                    for entity in entities['hashtags']:
                        tag = '#'+entity['text']
                        if tag not in hashtags:
                            requests.post(panoptic_url + 'hashtag', data={'topic' : entity['text'], 'token' : panoptic_token})
                        #Post mention to api
                        requests.post(panoptic_url + 'mention', data={'datetime' : datetime, 'topic' : entity['text'].lower(), 'sentiment' : sentiment, 'token' : panoptic_token, 'data' : 'twitter'})
                        #Post connection
                        requests.post(panoptic_url + 'connection', data={'userid' : user_id, 'hashtag' : entity['text'].lower(), 'tweetid' : tweet_id, 'action' : 'mention', 'token' : panoptic_token, 'data' : 'twitter'})
                        topics.append(entity['text'])

                if topics:
                    #print(topics)
                    tweetObj = {'service' : 'cdnpoli', 'name' : tweet['retweeted_status']['user']['name'], 'screen_name'  : tweet['retweeted_status']['user']['screen_name'], 'pic' : tweet['retweeted_status']['user']['profile_image_url'], 'tweet' : text.encode("utf-8"), 'link' : status_link, 'rt_count' : tweet['retweeted_status']['retweet_count'], 'fav_count' : tweet['retweeted_status']['favorite_count'], 'topics' : topics}
                    #print(json.dumps(tweetObj, indent=4, separators=(',', ': ')))
                    notify_node(tweetObj)
            except:
                pass

    return True

class MyListener(StreamListener):
    def on_data(self, data):
        try:
            return processData(data)

        except BaseException as e:
            print("Error on_data: %s" % str(e))

        return True

    def on_error(self, status):
        print(status)
        return False

auth = OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_secret)

query = getQuery()
while True:
    startStream()

    print('Twitter Restart','Restarting Twitter Stream...')
    time.sleep(60)
