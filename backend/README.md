# ShiftEase backend prototype

Flask + SQLAlchemy で作った試作用APIです。公開中のGitHub Pagesとは分離して `backend-prototype` ブランチで開発しています。

## 現在実装したもの
- 従業員番号ログイン
- 管理者PINログイン（試作用）
- セッションと権限分離
- 全員の確定シフト取得
- 自分のシフト希望取得・登録・変更
- 勤務不可 + メッセージ
- 欠勤/遅刻の記録
- 管理者ダッシュボード用データ
- 管理者だけのシフト登録
- 変更履歴
- 「この人いてほしい」用の非公開フラグ

## デモデータ
すべて架空です。
- 従業員: `0000` / 仲村 日向
- 管理者PIN: 環境変数 `ADMIN_PIN`。未設定時の開発用は `1234`

## ローカル起動
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python seed.py
python app.py
```

## 本番化する前に必須
- `SECRET_KEY` と `ADMIN_PIN` を環境変数へ設定
- SQLiteからPostgreSQL等へ変更
- HTTPS環境でSecure/HttpOnly/SameSite Cookieを設定
- 従業員番号だけの認証を本番で採用するか店舗側と再確認
- CORSを実際のフロントURLだけに限定
- CSRF対策、レート制限、ログ監査
- 個人情報を公開リポジトリへコミットしない

## 次の開発
1. フロントをAPI接続
2. 希望提出締切（1日/15日の運用）
3. 曜日・時間帯の「いつもの希望」
4. 必要人数（時間帯別）
5. 自動シフト生成
6. 5連勤・勤務不可・必要人数違反の警告/確認解除
7. シフト交換フロー
8. 通知（1日前 / 1時間前 / 15分前、未提出催促）
