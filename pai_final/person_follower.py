#!/usr/bin/env python3
"""
person_follower.py  ―  AI(YOLO)で人を見つけて追いかけるノード

流れ:
  1. Gazebo のカメラ画像 (/camera/image_raw) を受け取る
  2. YOLOv8 (学習済みモデル・推論のみ) で「person」を検出
  3. 人が画面の左右どちらにいるか / どのくらい大きく映っているか から
     速度指令 (/cmd_vel) を計算して publish
  4. 検出結果を描き込んだ画像を /ai/debug_image に publish (動画撮影用)

記事 (teleop_node.cpp) との対応:
  記事:   キー入力(KeyEvent) を subscribe → Twist を publish
  本課題: カメラ画像(Image)   を subscribe → AI で判断 → Twist を publish
"""
import time

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
from std_msgs.msg import String


class PersonFollower(Node):
    def __init__(self):
        super().__init__('person_follower')

        # ---- パラメータ (launch や コマンドで変更できる) ----
        self.declare_parameter('model', 'yolov8n.pt')        # 使うYOLOモデル
        self.declare_parameter('conf', 0.4)                  # 検出の信頼度しきい値
        self.declare_parameter('target_height', 0.62)        # 人の高さ/画像高さ がこの値になる距離で止まる
        self.declare_parameter('max_linear', 0.4)            # 前進の最大速度 [m/s]
        self.declare_parameter('max_angular', 1.0)           # 旋回の最大速度 [rad/s]
        self.declare_parameter('k_angular', 1.5)             # 旋回のゲイン
        self.declare_parameter('k_linear', 1.2)              # 前進のゲイン
        self.declare_parameter('search_angular', 0.4)        # 人を見失った時の探索回転速度
        self.declare_parameter('lost_timeout', 1.0)          # この秒数見えなければ探索モード
        self.declare_parameter('show_window', False)         # OpenCVウィンドウ表示
        self.declare_parameter('safe_ratio', 0.80)           # (改良) 人の高さ/画像高さ がこれ以上なら前進しない
        self.declare_parameter('deadband', 0.05)             # (改良) このくらいのずれは無視する (ブルブル防止)

        p = lambda n: self.get_parameter(n).value
        self.conf = p('conf')
        self.target_h = p('target_height')
        self.max_lin = p('max_linear')
        self.max_ang = p('max_angular')
        self.k_ang = p('k_angular')
        self.k_lin = p('k_linear')
        self.search_ang = p('search_angular')
        self.lost_timeout = p('lost_timeout')
        self.show_window = p('show_window')
        self.safe_ratio = p('safe_ratio')
        self.deadband = p('deadband')

        # ---- AIモデルの読み込み (初回はインターネットから自動ダウンロード) ----
        from ultralytics import YOLO
        self.get_logger().info(f"YOLOモデルを読み込み中: {p('model')}")
        self.model = YOLO(p('model'))
        self.get_logger().info('YOLOモデルの読み込み完了')

        # ---- publisher / subscriber (記事の teleop_node と同じ考え方) ----
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.debug_pub = self.create_publisher(Image, '/ai/debug_image', 10)
        self.state_pub = self.create_publisher(String, '/ai/state', 10)
        # (改良) 古い画像をためない: 保持するのは最新の1枚だけ
        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST, depth=1)
        self.sub = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, qos)

        self.last_seen = time.time()   # (改良) 起動直後にいきなり探索しない
        self.last_error = 0.0   # 最後に見えた方向 (探索時にそちらへ回る)
        self.busy = False
        # (改良) レポート用の計測
        self.prev_state = None
        self.state_count = {}
        self.infer_ms = 0.0
        self.last_log = time.time()

    # ------------------------------------------------------------------
    # ROS の Image メッセージ <-> numpy 配列 の変換
    # (cv_bridge を使わずに書くことで、numpy のバージョン問題を避ける)
    # ------------------------------------------------------------------
    @staticmethod
    def imgmsg_to_bgr(msg: Image) -> np.ndarray:
        ch = 4 if msg.encoding in ('rgba8', 'bgra8') else 3
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        arr = arr.reshape(msg.height, msg.step)[:, :msg.width * ch]
        arr = arr.reshape(msg.height, msg.width, ch)
        if msg.encoding == 'rgb8':
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        if msg.encoding == 'rgba8':
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        if msg.encoding == 'bgra8':
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        return arr.copy()  # bgr8

    @staticmethod
    def bgr_to_imgmsg(img: np.ndarray, header) -> Image:
        msg = Image()
        msg.header = header
        msg.height, msg.width = img.shape[:2]
        msg.encoding = 'bgr8'
        msg.step = msg.width * 3
        msg.data = img.tobytes()
        return msg

    # ------------------------------------------------------------------
    # メイン処理: 画像が届くたびに呼ばれる
    # ------------------------------------------------------------------
    def image_callback(self, msg: Image):
        if self.busy:          # AIの処理中に来た画像は捨てる (遅延防止)
            return
        self.busy = True
        try:
            frame = self.imgmsg_to_bgr(msg)
            h, w = frame.shape[:2]

            # ---- AI 推論: class 0 = person だけを検出 ----
            t0 = time.time()
            results = self.model(frame, classes=[0], conf=self.conf, verbose=False)
            ms = (time.time() - t0) * 1000.0   # (改良) 推論にかかった時間[ms]
            self.infer_ms = ms if self.infer_ms == 0.0 else 0.9 * self.infer_ms + 0.1 * ms
            boxes = results[0].boxes

            cmd = Twist()
            now = time.time()
            if boxes is not None and len(boxes) > 0:
                # 一番大きく映っている人(=一番近い人)を追いかける
                xyxy = boxes.xyxy.cpu().numpy()
                areas = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
                i = int(np.argmax(areas))
                x1, y1, x2, y2 = xyxy[i]
                score = float(boxes.conf[i])

                cx = (x1 + x2) / 2.0
                error_x = (cx - w / 2.0) / (w / 2.0)      # -1(左端) ~ +1(右端)
                height_ratio = (y2 - y1) / h               # 人の大きさ = 距離の目安

                # 旋回: 人が右にいれば右へ (ROSでは angular.z が負 = 右回り)
                ang = -self.k_ang * error_x
                if abs(error_x) < self.deadband:       # (改良) 小さなずれは無視
                    ang = 0.0
                cmd.angular.z = float(np.clip(ang, -self.max_ang, self.max_ang))
                # 前進: 人が小さく(遠く)映っていれば進む。近すぎたら少し下がる
                dist_error = self.target_h - height_ratio
                lin = self.k_lin * dist_error
                if abs(error_x) > 0.5:      # 大きくずれている時は旋回を優先
                    lin *= 0.3
                if abs(dist_error) < self.deadband:    # (改良) ちょうど良い距離なら動かない
                    lin = 0.0
                safe_stop = height_ratio > self.safe_ratio   # (改良) 近すぎたら下がらず止まる
                if safe_stop:
                    lin = 0.0
                cmd.linear.x = float(np.clip(lin, -0.15, self.max_lin))

                self.last_seen = now
                self.last_error = error_x
                state = 'FOLLOW'
                if abs(dist_error) < 0.05 and abs(error_x) < 0.1:
                    state = 'REACHED'
                if safe_stop:
                    state = 'SAFE_STOP'

                # 動画用: 検出結果を描画
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv2.putText(frame, f'person {score:.2f}', (int(x1), max(int(y1) - 8, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.line(frame, (int(cx), 0), (int(cx), h), (0, 255, 255), 1)
            elif now - self.last_seen > self.lost_timeout:
                # 見失った: 最後に見えた方向へその場で回って探す
                direction = -1.0 if self.last_error > 0 else 1.0
                cmd.angular.z = direction * self.search_ang
                state = 'SEARCH'
            else:
                state = 'WAIT'   # 一瞬見えなかっただけ → 停止して待つ

            # (改良) 状態が変わったらログ / 5秒ごとに推論速度をログ (レポートの数値に使える)
            if state != self.prev_state:
                self.state_count[state] = self.state_count.get(state, 0) + 1
                self.get_logger().info(f'状態 {self.prev_state} -> {state}  累計 {self.state_count}')
                self.prev_state = state
            if now - self.last_log > 5.0:
                self.get_logger().info(f'推論 {self.infer_ms:.0f} ms/枚 (約 {1000.0 / max(self.infer_ms, 1e-3):.1f} fps)')
                self.last_log = now

            self.cmd_pub.publish(cmd)
            self.state_pub.publish(String(data=state))

            # 画面中央線と状態表示
            cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
            color = {'FOLLOW': (0, 200, 0), 'REACHED': (255, 120, 0),
                     'SEARCH': (0, 0, 255), 'WAIT': (0, 200, 200),
                     'SAFE_STOP': (0, 120, 255)}[state]
            cv2.putText(frame, f'STATE: {state}', (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            cv2.putText(frame, f'v={cmd.linear.x:+.2f} m/s  w={cmd.angular.z:+.2f} rad/s',
                        (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            self.debug_pub.publish(self.bgr_to_imgmsg(frame, msg.header))

            if self.show_window:
                cv2.imshow('AI person follower', frame)
                cv2.waitKey(1)
        except Exception as e:  # エラーで止まらないようにログだけ出す
            self.get_logger().error(f'画像処理でエラー: {e}')
        finally:
            self.busy = False

    def stop_robot(self):
        self.cmd_pub.publish(Twist())


def main(args=None):
    rclpy.init(args=args)
    node = PersonFollower()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_robot()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
