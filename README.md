# PAI最終課題: AI（YOLO）で人を追いかける差動二輪ロボット

Gazebo（Fortress）と ROS 2（Humble）を連携させ、**ロボットのカメラ画像を AI（YOLOv8）で解析して、人を見つけて追いかける**シミュレーションです。

ベースにした記事: [gazeboとROS2を連携してロボットを操作する（Qiita, N622）](https://qiita.com/N622/items/9d89f77d85d9da0af29e)

| | ベース記事 | この課題（発展させた点） |
|---|---|---|
| 入力 | キーボード | **カメラ画像** |
| 判断 | 人間がキーを押す | **AI（YOLOv8）が人を検出して自動で判断** |
| ブリッジ | `/cmd_vel` のみ | `/cmd_vel` ＋ **カメラ画像** ＋ **オドメトリ** |
| 対象 | 静止したロボット操作 | **歩き回る人を追いかける**（見失ったら探す） |

---

## 0. 動作環境

- Ubuntu **22.04**（ROS 2 Humble は 22.04 用です）
- メモリ 8GB 以上推奨、GPU は不要（CPU で動きます）
- インターネット接続（初回に人モデルと YOLO モデルを自動ダウンロード）

---

## 1. 環境構築（最初の1回だけ）

```bash
# ワークスペースを作ってこのリポジトリを置く
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/<あなたのGitHub名>/pai_final.git

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
ros2 launch pai_final follow.launch.py
```

これ1行で次がすべて起動します。

1. Gazebo（ロボット・人・箱のワールド）
2. ros_gz_bridge（ROS 2 ⇔ Gazebo のトピック変換）
3. `person_follower`（AIノード）… 約5秒後
4. `person_mover`（人を8の字に歩かせる）… 約15秒後
5. `rqt_image_view`（AIの視界：検出枠・状態を表示）

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

## 4. 仕組み

```
 [Gazebo]                                  [ROS 2]
 カメラ  /camera ──bridge──▶ /camera/image_raw ──▶ person_follower (YOLOv8)
                                                    │  人の位置・大きさから
 差動二輪 /cmd_vel ◀─bridge── /cmd_vel ◀────────────┘  速度を計算
                                                    └──▶ /ai/debug_image (動画用)
```

- **旋回**: 人が画面の右にいれば右へ回る（`angular.z = -k × ずれ`）
- **前進**: 人が小さく（遠く）映っていれば前進、大きく（近く）なれば止まる
- **探索**: 1秒以上見失ったら、最後に見えた方向へその場で回って探す

状態は `FOLLOW`（追従）/ `REACHED`（到着）/ `WAIT`（一瞬見失い）/ `SEARCH`（探索）の4つ。

### 主なパラメータ（`person_follower`）

| 名前 | 初期値 | 意味 |
|---|---|---|
| `target_height` | 0.62 | 人の高さ÷画像の高さ がこの値で停止（大きくすると近づく） |
| `max_linear` | 0.4 | 最大前進速度 [m/s] |
| `k_angular` | 1.5 | 旋回の強さ |
| `conf` | 0.4 | 検出の信頼度しきい値 |

---

## 5. ファイル構成

```
pai_final/
├── launch/follow.launch.py        # 全部まとめて起動
├── worlds/follow_world.sdf        # ワールド＋カメラ付きロボット
├── config/bridge.yaml             # ブリッジ設定
├── pai_final/person_follower.py   # AIノード（YOLOで人を検出→追従）
├── pai_final/person_mover.py      # 人を歩かせるデモ用ノード
├── tools/setup_env.sh             # 環境構築スクリプト
├── package.xml / setup.py / setup.cfg
└── README.md
```

## 6. ライセンス・クレジット

- 人モデル: [Standing person（OpenRobotics, Gazebo Fuel）](https://fuel.gazebosim.org/1.0/OpenRobotics/models/Standing%20person) — CC0 1.0
- 物体検出: [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)（AGPL-3.0）
- ベース記事: [N622 / Qiita](https://qiita.com/N622/items/9d89f77d85d9da0af29e)
