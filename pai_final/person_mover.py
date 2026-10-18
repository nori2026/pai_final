#!/usr/bin/env python3
"""
person_mover.py  ―  Gazebo 上の「人」をゆっくり歩かせるノード (デモ用)

人が動くことで「AIが人を追いかけている」ことが動画で分かりやすくなります。
Gazebo の set_pose サービスを `ign service` コマンドで呼び出して、人の位置を更新します。
(手で動かしたい場合は、このノードを起動せずに Gazebo 画面の移動ツールで人をドラッグしてもOK)
"""
import math
import subprocess

import rclpy
from rclpy.node import Node


class PersonMover(Node):
    def __init__(self):
        super().__init__('person_mover')
        self.declare_parameter('world', 'follow_world')
        self.declare_parameter('model_name', 'person')
        self.declare_parameter('center_x', 3.5)
        self.declare_parameter('center_y', 0.0)
        self.declare_parameter('radius_x', 1.5)   # 横8の字の大きさ
        self.declare_parameter('radius_y', 2.0)
        self.declare_parameter('period', 90.0)    # 1周にかかる秒数 (大きいほどゆっくり)
        self.declare_parameter('rate', 5.0)       # 位置更新の回数/秒

        g = lambda n: self.get_parameter(n).value
        self.service = f"/world/{g('world')}/set_pose"
        self.name = g('model_name')
        self.cx, self.cy = g('center_x'), g('center_y')
        self.rx, self.ry = g('radius_x'), g('radius_y')
        self.period = g('period')
        self.t0 = self.get_clock().now()
        self.timer = self.create_timer(1.0 / g('rate'), self.on_timer)
        self.get_logger().info(f'人モデル "{self.name}" を動かします ({self.service})')

    def on_timer(self):
        t = (self.get_clock().now() - self.t0).nanoseconds * 1e-9
        th = 2.0 * math.pi * t / self.period
        # 8の字 (リサージュ曲線) で歩く
        x = self.cx + self.rx * math.sin(2 * th)
        y = self.cy + self.ry * math.sin(th)
        # 進行方向を向かせる (人モデルは +Y 方向が正面なので -90度補正)
        dx = 2 * self.rx * math.cos(2 * th)
        dy = self.ry * math.cos(th)
        yaw = math.atan2(dy, dx) + math.pi / 2
        qz, qw = math.sin(yaw / 2), math.cos(yaw / 2)
        req = (f'name: "{self.name}", position: {{x: {x:.3f}, y: {y:.3f}, z: 0}}, '
               f'orientation: {{x: 0, y: 0, z: {qz:.4f}, w: {qw:.4f}}}')
        subprocess.Popen(
            ['ign', 'service', '-s', self.service,
             '--reqtype', 'ignition.msgs.Pose', '--reptype', 'ignition.msgs.Boolean',
             '--timeout', '300', '--req', req],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(args=None):
    rclpy.init(args=args)
    node = PersonMover()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
