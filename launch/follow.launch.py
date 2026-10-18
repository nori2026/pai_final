"""
follow.launch.py ― このファイル1つで全部起動します

  ros2 launch pai_final follow.launch.py                 # AI追従モード(人が自動で歩く)
  ros2 launch pai_final follow.launch.py move_person:=false   # 人は止めたまま
  ros2 launch pai_final follow.launch.py use_ai:=false   # AIなし(キーボード操作で練習)

起動するもの:
  1. Gazebo (ワールド: worlds/follow_world.sdf)
  2. ros_gz_bridge (config/bridge.yaml の設定で ROS2 <-> Gazebo を変換)
  3. person_follower (AIノード)      ※ use_ai:=true の時
  4. person_mover (人を歩かせる)     ※ move_person:=true の時
  5. rqt_image_view (AIの視界を表示) ※ show_image:=true の時
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('pai_final')
    world = os.path.join(pkg_share, 'worlds', 'follow_world.sdf')
    bridge_yaml = os.path.join(pkg_share, 'config', 'bridge.yaml')

    use_ai = LaunchConfiguration('use_ai')
    move_person = LaunchConfiguration('move_person')
    show_image = LaunchConfiguration('show_image')

    # 1. Gazebo を起動 (-r: 起動と同時にシミュレーション開始)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('ros_gz_sim'),
                         'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': f'-r {world}'}.items(),
    )

    # 2. ブリッジ (記事の「configファイルでまとめてブリッジ」と同じ方法)
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        parameters=[{'config_file': bridge_yaml}],
        output='screen',
    )

    # 3. AI ノード (Gazebo の起動を少し待ってから開始)
    follower = TimerAction(period=5.0, actions=[Node(
        package='pai_final',
        executable='person_follower',
        output='screen',
        condition=IfCondition(use_ai),
    )])

    # 4. 人を歩かせるノード (AIの準備が終わる頃から開始)
    mover = TimerAction(period=15.0, actions=[Node(
        package='pai_final',
        executable='person_mover',
        output='screen',
        condition=IfCondition(move_person),
    )])

    # 5. AIの視界(検出結果入り)を表示するウィンドウ
    viewer = Node(
        package='rqt_image_view',
        executable='rqt_image_view',
        arguments=['/ai/debug_image'],
        condition=IfCondition(show_image),
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_ai', default_value='true'),
        DeclareLaunchArgument('move_person', default_value='true'),
        DeclareLaunchArgument('show_image', default_value='true'),
        gazebo,
        bridge,
        follower,
        mover,
        viewer,
    ])
