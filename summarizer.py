#!/usr/bin/env python3
# https://github.com/masuidrive/slack-summarizer
# by [masuidrive](https://twitter.com/masuidrive) @ [Bloom&Co., Inc.](https://www.bloom-and-co.com/) 2023- [APACHE LICENSE, 2.0](https://www.apache.org/licenses/LICENSE-2.0)
import os
import re
import time
import backoff
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, time
from slack_sdk.errors import SlackApiError
from slack_sdk import WebClient

import openai

openai.api_key = str(os.environ.get('OPEN_AI_TOKEN')).strip()

# APIトークンとチャンネルIDを設定する
TOKEN = str(os.environ.get('SLACK_BOT_TOKEN')).strip()
SLACK_DOMAIN = str(os.environ.get('SLACK_DOMAIN')).strip()
CHANNEL_ID = str(os.environ.get('SLACK_POST_CHANNEL_ID')).strip()
# 要約チャンネルは無視する。,で複数指定されることを想定している
SUMMARY_CHANNEL_IDS = str(os.environ.get('SUMMARY_CHANNEL_IDS')).strip().split(',')

# 取得する期間を計算する
SUMMARY_TARGET_CHAT_COUNT_LENGTH = 3
SUMMARY_TARGET_TEXT_LENGTH = 300
REQUEST_CHANNEL_LIMIT = 999
# 昨日0時から今日0時を範囲とする
JST = ZoneInfo('Asia/Tokyo')
now = datetime.now(JST)
start_of_today = datetime(now.year, now.month, now.day, tzinfo=JST)
start_of_yesterday = start_of_today - timedelta(days=1)
start_time = datetime.combine(start_of_yesterday, time.min).replace(tzinfo=JST)
end_time = datetime.combine(start_of_today, time.min).replace(tzinfo=JST)

# Slack APIクライアントを初期化する
client = WebClient(token=TOKEN)

# OpenAIのAPIを使って要約を行う
@backoff.on_exception(backoff.expo, openai.error.RateLimitError)
def summarize(_text):
    print('summarize:start')
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0.3,
        messages=[
            {"role": "system", "content": "チャットログのフォーマットは、「本文\\n」である。「\\n」は改行である。チャットログは「&&」で複数人のチャットが連結されている。ごはん、トイレ、体調を気にしている場合は猫のチャンネルである。猫のチャンネルの場合、発言者たちはその猫、あるいは複数の猫たちの事を会話している。猫の名前はひらがな、カタカナ、漢字、愛称、くんづけ、ちゃんづけで同じ猫を指していることがある。「まつとたけ」のように複数の猫を扱っていることがある。猫のチャンネルでない場合は、保護猫団体の会運営について会話している。過去のチャットログは含まれないので意味を失っている可能性がある。以上を踏まえて指示に従え"},
            {"role": "user", "content": f"「- 猫の名前: \\n- 健康状態：\\n- 薬：\\n- 食事：\\n- トイレ：\\n- その他：」のフォーマットを使用し、該当する行の「：」の右に内容を要約する(内容なし、特に記載なし、不明な場合は「不明」と記載する)。要約が元々のチャットログを改編してミスリードを起こす内容にならないよう事実を述べるよう厳重に注意する。以上を踏まえて、下記を箇条書きで要約せよ。\n\n{_text}"}
        ]
    )
    print('summarize:end')
    return response["choices"][0]["message"]['content']

# 指定したチャンネルの履歴を取得する
def load_merge_message(channel_id):
    result = None
    try:
        result = client.conversations_history(
            channel=channel_id,
            oldest=start_time.timestamp(),
            latest=end_time.timestamp(),
            limit=200,
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
    first_message_ts = result["messages"][-1]['ts']

    while result["has_more"]:
        result = client.conversations_history(
            channel=channel_id,
            oldest=start_time.timestamp(),
            latest=end_time.timestamp(),
            cursor=result["response_metadata"]["next_cursor"]
        )
        print('result has_more', result)
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

    strip_messages_text = [re.sub(r"[a-zA-Z0-9._-]+:", "", msg).strip() for msg in messages_text]
    # print('strip_messages_text', strip_messages_text)

    # リストからテキストを結合して文字列を作成
    merge_message_text = "&&".join(strip_messages_text)

    # メッセージがチャット回数、チャット長さが規定未満はNoneとして対象外とする
    if len(strip_messages_text) < SUMMARY_TARGET_CHAT_COUNT_LENGTH and len(merge_message_text) < SUMMARY_TARGET_TEXT_LENGTH:
        return None
    else:
        return merge_message_text, first_message_ts


# ユーザーIDからユーザー名に変換するために、ユーザー情報を取得する
channels = []
try:
    users_info = client.users_list()
    users = users_info['members']
    users = [user for user in users if user['deleted'] == False]
    print('users', users)
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
    channels = [entry for entry in channels if entry['name'].startswith(('-', '_'))]
    channels = sorted(channels, key=lambda x: int(re.findall(
        r'\d+', x["name"])[0]) if re.findall(r'\d+', x["name"]) else float('inf'))
    print('channels', channels)
    print('len(channels)', len(channels))
except SlackApiError as e:
    print("Error : {}".format(e))
    exit(1)

long_messages = []
# 全てのチャンネルからメッセージを読み込む
for channel in channels:
    if channel["id"] in SUMMARY_CHANNEL_IDS:
        continue

    _load_merge_message = load_merge_message(channel["id"])
    if _load_merge_message is None:
        continue

    message, first_ts = _load_merge_message

    long_message_dict = {"channel_id": channel["id"], "message": message, "first_ts": first_ts}
    long_messages.append(long_message_dict)

# メッセージ長で並び替え、先頭REQUEST_CHANNEL_LIMITの辞書を取得する
sorted_messages = sorted(long_messages, key=lambda x: len(x['message']), reverse=True)[:REQUEST_CHANNEL_LIMIT]

print('len(sorted_messages): ', len(sorted_messages))

result_text = []
for message in sorted_messages:
    print('message', message)
    # lines = summarize(message['message']).split('\n')
    # filtered_lines = [line for line in lines if "：不明" not in line]
    # text = '\n'.join(filtered_lines)
    #
    # ts = 'p' + message['first_ts'].replace('.', '')
    # first_link = f"{SLACK_DOMAIN}/archives/{message['channel_id']}/{ts}"
    #
    # result_text.append(f"<#{message['channel_id']}> {first_link}\n{text}")

title = f"{start_of_yesterday.strftime('%Y/%m/%d')}の要約ニャン"

response = client.chat_postMessage(
    channel=CHANNEL_ID,
    type="mrkdwn",
    text=title + "\n\n" + "\n\n".join(result_text) + "\n\n★AIによる要約は誤りが含まれることがあります。前回投稿の考慮も欠如しています。日毎の出来毎を残し、理解と見返しを助ける事が目的です。\n★お薬や体調に関することは実際のチャンネルを追いかけたり、お世話マニュアルはなるべく読む、一緒にお世話に入っている方やSlackで状況を聞くようにしてください",
)
print("Message posted: ", response["ts"])
