# PAI最終課題: AI（YOLO）で人を追いかける差動二輪ロボット

Gazebo（Fortress）と ROS 2（Humble）を連携させ、**ロボットのカメラ画像を AI（YOLOv8）で解析して、人を見つけて追いかける**シミュレーションです。
追従中の「状態のばたつき」を抑える工夫（ヒステリシス）を入れ、**状態の切り替え回数を約49%減らしました**（4章）。

- デモ動画: YouTube「PAI最終課題_norihousou」（チャンネル `@norihousou`）
- ベースにした記事: [gazeboとROS2を連携してロボットを操作する（Qiita, N622）](https://qiita.com/N622/items/9d89f77d85d9da0af29e)

| | ベース記事 | この課題（発展させた点） |
|---|---|---|
| 入力 | キーボード | **カメラ画像** |
| 判断 | 人間がキーを押す | **AI（YOLOv8）が人を検出して自動で判断** |
| ブリッジ | `/cmd_vel` のみ | `/cmd_vel` ＋ **カメラ画像** ＋ **オドメトリ** |
| 対象 | 静止したロボット操作 | **歩き回る人を追いかける**（近づきすぎたら安全停止、見失ったら探す） |
| 安定性 | － | **最新フレーム優先・不感帯・ヒステリシス** |

---

## 0. 動作環境

- Ubuntu **22.04**（ROS 2 Humble は 22.04 用です）。Windows の場合は WSL2 上の Ubuntu 22.04 で動作確認しました
- メモリ 8GB 以上推奨、GPU は不要（CPU で動きます）
- インターネット接続（初回に YOLO モデルを自動ダウンロード）

---

## 1. 環境構築（最初の1回だけ）

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/nori2026/pai_final.git

# 必要なソフトをまとめてインストール（10〜30分）
cd ~/ros2_ws/src/pai_final
bash tools/setup_env.sh
```

終わったら **ターミナルを閉じて開き直す**。

---

## 2. ビルド

```bash
cd ~/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

> `source install/setup.bash` は **新しいターミナルを開くたびに** 必要です。

---

## 3. 実行

```bash
# WSL2 など GPU 描画が使えない環境では、ソフトウェア描画にします（Gazebo が落ちるのを防ぐ）
export LIBGL_ALWAYS_SOFTWARE=1
# 人モデルはこのリポジトリ内（models/）を使います
export IGN_GAZEBO_RESOURCE_PATH=$HOME/ros2_ws/src/pai_final/models

ros2 launch pai_final follow.launch.py
```

この1行で次がすべて起動します。

1. Gazebo（ロボット・人・箱のワールド）
2. ros_gz_bridge（ROS 2 ⇔ Gazebo のトピック変換）
3. `person_follower`（AIノード）… 約5秒後
4. `person_mover`（人を8の字に歩かせる）… 約15秒後
5. `rqt_image_view`（AIの視界：検出枠・状態・速度を表示）

### オプション

```bash
ros2 launch pai_final follow.launch.py move_person:=false   # 人は止めたまま（自分でドラッグして動かす）
ros2 launch pai_final follow.launch.py use_ai:=false        # AIなし（キーボード練習用）
```

キーボード練習（`use_ai:=false` で起動後、別ターミナルで）:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

---

## 4. 仕組みと工夫点

```
 [Gazebo]                                  [ROS 2]
 カメラ  /camera ──bridge──▶ /camera/image_raw ──▶ person_follower (YOLOv8)
                                                    │  人の位置・大きさから
 差動二輪 /cmd_vel ◀─bridge── /cmd_vel ◀────────────┘  速度を計算
                                                    └──▶ /ai/debug_image (動画用)
```

- **旋回**: 人が画面の右にいれば右へ回る（`angular.z = -k × ずれ`）
- **前進**: 人が小さく（遠く）映っていれば前進、大きく（近く）なれば止まる／下がる
- **探索**: 1秒以上見失ったら、最後に見えた方向へその場で回って探す

状態は5つです。

| 状態 | 意味 | 画面の色 |
|---|---|---|
| `FOLLOW` | 人を追従中 | 緑 |
| `REACHED` | 目標距離に到着して停止 | 青 |
| `SAFE_STOP` | 近づきすぎたので安全停止 | オレンジ |
| `WAIT` | 一瞬見失った（少し待つ） | 黄 |
| `SEARCH` | 見失ったので、その場で回って探索 | 赤 |

### 工夫点（自分で加えた改良）

| # | 工夫 | 内容 | 狙い |
|---|---|---|---|
| 1 | 最新フレーム優先 | 画像の購読を QoS `KEEP_LAST depth=1`・`BEST_EFFORT` にした | CPU推論が遅い時に古い画像が溜まらず、遅延を防ぐ |
| 2 | 不感帯（deadband） | 目標距離の±5%以内は前進速度を0にする | 停止付近の小刻みな前後動作を防ぐ |
| 3 | 安全停止（SAFE_STOP） | 人の高さ比が 0.80 を超えたら停止 | 近づきすぎ・衝突を防ぐ |
| 4 | 処理時間のログ | 推論時間（EMA）と fps を5秒ごとに表示 | CPUで実用になるか数値で確認する |
| 5 | **ヒステリシス** | SAFE_STOP は「入る 0.80／出る 0.75」、REACHED は有効中だけ判定幅を1.6倍にする | **しきい値付近での状態のばたつき（チャタリング）を抑える** |

### ヒステリシスの効果（実験）

同じワールド・同じ人の動き（約6.5分）で、ヒステリシスなし（v1）と、あり（v2）を比べました。

| 指標（約385秒あたり） | v1（なし） | v2（あり） |
|---|---|---|
| 状態切り替えの合計 | 116 回 | 59 回（**−49%**） |
| FOLLOW → SAFE_STOP | 21 回 | 8 回 |
| SAFE_STOP → FOLLOW | 19 回 | 5 回 |
| REACHED ⇔ FOLLOW | 25 回 | 15 回 |

- 推論時間は約 62〜70 ms/枚（約 14〜17 fps、CPUのみ）でした。
- 注意: 各条件とも1回ずつの測定です。傾向は分かりますが、統計的な評価ではありません。
- ログは個人情報（ユーザー名）を含むため、リポジトリには含めていません。

### 主なパラメータ（`person_follower`）

| 名前 | 初期値 | 意味 |
|---|---|---|
| `target_height` | 0.62 | 人の高さ÷画像の高さ がこの値で停止（大きくすると近づく） |
| `safe_ratio` | 0.80 | これを超えたら安全停止 |
| `hysteresis` | 0.05 | 安全停止から復帰するときの余裕 |
| `deadband` | 0.05 | 目標距離付近で前進しない幅 |
| `max_linear` | 0.4 | 最大前進速度 [m/s] |
| `k_angular` | 1.5 | 旋回の強さ |
| `conf` | 0.4 | 検出の信頼度しきい値 |

---

## 5. 開発中に分かったこと（つまずきと対処）

| 問題 | 原因 | 対処 |
|---|---|---|
| Gazebo Fuel（モデル配布サーバー）が 502 で人モデルを取得できない | サーバー側の障害 | 人モデルをリポジトリの `models/person_standing/` に同梱し、ワールドを `model://person_standing` に変更 |
| WSL2 で Gazebo が `GL3PlusTextureGpu::copyTo` で落ちる | WSLg の GPU 描画（ogre2）の非対応 | `LIBGL_ALWAYS_SOFTWARE=1` でソフトウェア描画にした |
| `Host unreachable` の警告が出る | `person_mover` が `ign service` を呼ぶ時の警告 | 動作に影響しないため、そのままにした |
| 近づく・止まるの付近で状態が頻繁に切り替わる | しきい値ちょうどで判定がゆらぐ | ヒステリシスを導入（上記） |

---

## 6. ファイル構成

```
pai_final/
├── launch/follow.launch.py        # 全部まとめて起動
├── worlds/follow_world.sdf        # ワールド＋カメラ付きロボット
├── models/person_standing/        # 人モデル（同梱）
├── config/bridge.yaml             # ブリッジ設定
├── pai_final/person_follower.py   # AIノード（YOLOで人を検出→追従）
├── pai_final/person_mover.py      # 人を歩かせるデモ用ノード
├── tools/setup_env.sh             # 環境構築スクリプト
├── package.xml / setup.py / setup.cfg
└── README.md
```

## 7. ライセンス・クレジット

- 人モデル: [osrf/gazebo_models](https://github.com/osrf/gazebo_models) の `person_standing`（作者: Marina Kollmitz、Makehuman で作成。ライセンスは配布元リポジトリの表示に従う）
- 物体検出: [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)（AGPL-3.0）
- ベース記事: [N622 / Qiita](https://qiita.com/N622/items/9d89f77d85d9da0af29e)
- 開発では AI（Claude）を、設計の相談、コードの改良、実験の整理に使用しました。
