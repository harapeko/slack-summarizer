# ChatGPT を使って Slack の Public channel をまとめて要約するスクリプト

by [masuidrive](https://twitter.com/masuidrive) @ [Bloom&Co., Inc.](https://www.bloom-and-co.com/) 2023-
[APACHE LICENSE, 2.0](https://www.apache.org/licenses/LICENSE-2.0)

![](https://raw.githubusercontent.com/masuidrive/slack-summarizer/main/images/slack-summarized.png)

Slack の Public channel の要約を作って投稿するスクリプトです。

チャンネルが増えた組織では読むのが追いつかないことが多いため、要約を作って投稿することで、チャンネルの活動を把握しやすくすることができます。

このコードの大半も ChatGPT を使って書きました。とりあえず動くように書いただけなので、コードは雑然としています。

誰かキレイにしたら Pull Request ください。機能追加なども大歓迎です。

簡単な解説などはこちらの記事に書いています。

https://note.com/masuidrive/n/na0ebf8a4c4f0

## How to set it up

GitHub Actions で毎週土曜日の午前 7 時に、公開チャンネルごとに1週間分のテキストを取得して動くようになっています。これ以外の環境で動かす場合は適当に頑張ってください。

※短いテキストは無視するようにしています

### 自分の GitHub アカウントに fork する

- 右上の"Fork"ボタンを押して、自分のリポジトリに fork します
- 有料プランにするなどして GitHub Actions が実行できるようにしておきます

### 環境変数を設定する

- "Settings"タブを開き、左の"Secrets and variables"→"Actions"を開きます
- 右上の緑の"New Repository Secret"をクリックすると環境変数が設定できるので、次の 3 つの変数を設定します

![](https://raw.githubusercontent.com/masuidrive/slack-summarizer/main/images/github-settings.png)

#### OPEN_AI_TOKEN

- OpenAI の認証トークン
- [OpenAI の Web サイト](https://openai.com/)にアクセスしてください
- 右上の"Sign In"ボタンをクリックし、アカウントにログインしてください
- ページ上部の"API"メニューから、"API Key"をクリックして、API キーを生成します
- "API Key"ページにアクセスすると、API キーが表示されます。これをコピーして Value に貼り付けます

#### SLACK_BOT_TOKEN

- Slack の API 認証トークン
- [Slack API の Web サイト](https://api.slack.com/)にアクセスし、ログインしてください
- "Create a new app"をクリックして、"From an app manifest"を選択し manifest に下記の内容をコピーします

```
{"display_information":{"name":"Summary","description":"Public channelのサマリーを作る","background_color":"#d45f00"},"features":{"bot_user":{"display_name":"Summary","always_online":false}},"oauth_config":{"scopes":{"bot":["channels:history","channels:join","channels:read","chat:write","users:read"]}},"settings":{"org_deploy_enabled":true,"socket_mode_enabled":false,"token_rotation_enabled":false}}
```

- 画面左の"Install App"をクリックし、右に出る"Install App to Workspace"をクリックして、アプリをワークスペースにインストールします。インストールが完了すると、bot の OAuth アクセストークンが表示されます
- この`xoxb-`で始まるトークンをコピーして Value に貼り付けます

#### SLACK_DOMAIN

- SLACKワークスペースのドメイン
- 例：example.slack.com
- チャンネルごとの最初のメッセージリンクを作成するのに使用する(日付移動の代替)

#### SLACK_POST_CHANNEL_ID

- 要約結果を投稿する Slack の channel_id
- Slack で要約結果を投稿したいチャンネルを開きます
- 上部のチャンネル名をクリックし、出てきた Popup の最下部にある Channel ID を Value に貼り付けます

#### SUMMARY_CHANNEL_IDS

- 要約結果を投稿しているチャンネルをスキップするための設定
- 要約結果を投稿している Slack の channel_id(一週間、一月など複数の要約チャンネルが出来ることを考慮して複数指定を想定している)
- Slack で要約結果を投稿しているチャンネルを順次開きます
- 上部のチャンネル名をクリックし、出てきた Popup の最下部にある Channel ID を Value に貼り付けます
- チャンネルが複数ある場合は「`,`」で繋いでください

### Channel に bot をインストール

- 画面上部の検索窓から"Summarizer"を検索し、"Summarizer [APP]"をクリックします。
- 上の"Summarizer"をクリックし、"Add this app to a channel"をクリックして、要約結果を投稿したいチャンネルを指定します

### 実行

- GitHub のリポジトリで"Settings"タブを開き、左の"Actions"→"General"を開きます
- "Actions permissions"の"Allow all actions and reusable workflows"を選択して保存してください

これらの設定をすると、cron設定により Slack の Public channel の要約結果が投稿されます。

手動で実行してみる場合には"Actions" タブを開き、左の"Summarizer"をクリックして、右の"Run workflow"をおしてください。

## Problems

~~このスクリプトで既知の課題としては、1 チャンネル当たりの発言が 4000token を超えるとコケます。分割する部分は書いてないので。Pull Request をお待ちしてます → 誰か~~

→backoffを使用して対応済み
