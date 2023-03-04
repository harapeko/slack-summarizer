#!/usr/bin/env python3
# https://github.com/masuidrive/slack-summarizer
# by [masuidrive](https://twitter.com/masuidrive) @ [Bloom&Co., Inc.](https://www.bloom-and-co.com/) 2023- [APACHE LICENSE, 2.0](https://www.apache.org/licenses/LICENSE-2.0)
import os
import re
import time
import pytz
import backoff
from slack_sdk.errors import SlackApiError
from slack_sdk import WebClient
from datetime import datetime, timedelta

import openai

openai.api_key = str(os.environ.get('OPEN_AI_TOKEN')).strip()

# APIトークンとチャンネルIDを設定する
TOKEN = str(os.environ.get('SLACK_BOT_TOKEN')).strip()
CHANNEL_ID = str(os.environ.get('SLACK_POST_CHANNEL_ID')).strip()

# 取得する期間を計算する
HOURS_BACK = 25
SUMMARY_TARGET_CHAT_COUNT_LENGTH = 3
SUMMARY_TARGET_TEXT_LENGTH = 300
REQUEST_CHANNEL_LIMIT = 999
JST = pytz.timezone('Asia/Tokyo')
now = datetime.now(JST)
yesterday = now - timedelta(hours=HOURS_BACK)
start_time = datetime(yesterday.year, yesterday.month, yesterday.day,
                      yesterday.hour, yesterday.minute, yesterday.second)
end_time = datetime(now.year, now.month, now.day,
                    now.hour, now.minute, now.second)

# Slack APIクライアントを初期化する
client = WebClient(token=TOKEN)


# 指定したチャンネルの履歴を取得する
def load_merge_message(channel_id):
    result = None
    try:
        result = client.conversations_history(
            channel=channel_id,
            oldest=start_time.timestamp(),
            latest=end_time.timestamp()
        )
    except SlackApiError as e:
        if e.response['error'] == 'not_in_channel':
            response = client.conversations_join(
                channel=channel_id
            )
            if not response["ok"]:
                raise SlackApiError("conversations_join() failed")
            time.sleep(5)  # チャンネルにjoinした後、少し待つ

            result = client.conversations_history(
                channel=channel_id,
                oldest=start_time.timestamp(),
                latest=end_time.timestamp()
            )
        else:
            print("Error : {}".format(e))
            return None

    # messages = result["messages"]
    _messages = list(filter(lambda m: "subtype" not in m, result["messages"]))

    if len(_messages) < 1:
        return None

    messages_text = []

    while result["has_more"]:
        result = client.conversations_history(
            channel=channel_id,
            oldest=start_time.timestamp(),
            latest=end_time.timestamp(),
            cursor=result["response_metadata"]["next_cursor"]
        )
        _messages.extend(result["messages"])
    for _message in _messages[::-1]:
        if "bot_id" in _message:
            continue
        if _message["text"].strip() == '':
            continue
        # ユーザーIDからユーザー名に変換する
        user_id = _message['user']
        sender_name = None
        for user in users:
            if user['id'] == user_id:
                sender_name = user['name']
                break
        if sender_name is None:
            sender_name = user_id

        # テキスト取り出し
        _text = _message["text"].replace("\n", "\\n")

        # メッセージ中に含まれるユーザーIDやチャンネルIDを名前やチャンネル名に展開する
        matches = re.findall(r"<@[A-Z0-9]+>", _text)
        for match in matches:
            user_id = match[2:-1]
            user_name = None
            for user in users:
                if user['id'] == user_id:
                    user_name = user['name']
                    break
            if user_name is None:
                user_name = user_id
            _text = _text.replace(match, f"@{user_name} ")

        matches = re.findall(r"<#[A-Z0-9]+>", _text)
        for match in matches:
            channel_id = match[2:-1]
            channel_name = None
            for channel in channels:
                if channel['id'] == channel_id:
                    channel_name = channel['name']
                    break
            if channel_name is None:
                channel_name = channel_id
            _text = _text.replace(match, f"#{channel_name} ")
        messages_text.append(f"{sender_name}: {_text}")

    strip_messages_text = [re.sub(r"[a-zA-Z0-9._-]+: ", "", msg)
                           .replace(":sweat_drops:", "")
                           .replace("\\n", "")
                           .strip()
                           for msg in messages_text]
    print('strip_messages_text', strip_messages_text)

    # リストからテキストを結合して文字列を作成
    merge_message_text = "&&".join(strip_messages_text)

    # メッセージがチャット回数、チャット長さが規定未満はNoneとして対象外とする
    if len(strip_messages_text) < SUMMARY_TARGET_CHAT_COUNT_LENGTH and len(merge_message_text) < SUMMARY_TARGET_TEXT_LENGTH:
        return None
    else:
        return merge_message_text


# OpenAIのAPIを使って要約を行う
@backoff.on_exception(backoff.expo, openai.error.RateLimitError)
def summarize(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0.5,
        messages=[
            {"role": "system", "content": "複数の本文が&&で連結されている事を踏まえて指示に従え"},
            {"role": "user", "content": f"下記を箇条書きで要約しろ。1行ずつの説明ではない。全体は短く理解しやすく\n\n{text}"}
        ]
    )
    return response["choices"][0]["message"]['content']


# ユーザーIDからユーザー名に変換するために、ユーザー情報を取得する
try:
    users_info = client.users_list()
    users = users_info['members']
except SlackApiError as e:
    print("Error : {}".format(e))
    exit(1)

# チャンネルIDからチャンネル名に変換するために、チャンネル情報を取得する
try:
    channels_info = client.conversations_list(
        types="public_channel",
        exclude_archived=True,
    )
    channels = [channel for channel in channels_info['channels']
                if not channel["is_archived"] and channel["is_channel"]]
    channels = sorted(channels, key=lambda x: int(re.findall(
        r'\d+', x["name"])[0]) if re.findall(r'\d+', x["name"]) else float('inf'))
except SlackApiError as e:
    print("Error : {}".format(e))
    exit(1)

# 300文字を超過するメッセージを格納するリストを作成する
long_messages = []
print('len(channels)', len(channels))
# 全てのチャンネルからメッセージを読み込む
for channel in channels:
    message = load_merge_message(channel["id"])
    if message is None:
        continue

    long_message_dict = {"channel_id": channel["id"], "message": message}
    long_messages.append(long_message_dict)

# メッセージ長で並び替え、先頭REQUEST_CHANNEL_LIMITの辞書を取得する
sorted_messages = sorted(long_messages, key=lambda x: len(x['message']), reverse=True)[:REQUEST_CHANNEL_LIMIT]

print('len(sorted_messages): ', len(sorted_messages))
print('sorted_messages', sorted_messages)

result_text = []
for message in sorted_messages:
    text = summarize(message['message'])
    result_text.append(f"----\n<#{message['channel_id']}>\n{text}")

title = f"{yesterday.strftime('%Y/%m/%d')}の要約ニャン"

response = client.chat_postMessage(
    channel=CHANNEL_ID,
    text=title + "\n\n" + "\n\n".join(result_text)
)
print("Message posted: ", response["ts"])
