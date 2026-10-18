#!/bin/bash
# =====================================================================
#  PAI最終課題 環境構築スクリプト (Ubuntu 22.04 専用)
#  ROS 2 Humble + Gazebo Fortress + ros_gz + YOLO(ultralytics) を入れます
#
#  使い方:  bash tools/setup_env.sh
#  (途中でパスワードを聞かれたら、Ubuntuのログインパスワードを入力)
# =====================================================================
set -e

echo "===== [0/6] Ubuntu のバージョン確認 ====="
. /etc/os-release
echo "OS: $PRETTY_NAME"
if [ "$VERSION_CODENAME" != "jammy" ]; then
  echo "!! このスクリプトは Ubuntu 22.04 (jammy) 用です。ROS 2 Humble は 22.04 で使ってください。"
  exit 1
fi

echo "===== [1/6] 文字コード(ロケール)の設定 ====="
sudo apt-get update
sudo apt-get install -y locales software-properties-common curl gnupg lsb-release
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

echo "===== [2/6] ROS 2 の apt リポジトリを登録 ====="
sudo add-apt-repository -y universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt-get update

echo "===== [3/6] ROS 2 Humble + Gazebo Fortress + ブリッジ をインストール (10〜30分) ====="
sudo apt-get install -y \
  ros-humble-desktop \
  ros-humble-ros-gz \
  ros-humble-rqt-image-view \
  ros-humble-teleop-twist-keyboard \
  python3-colcon-common-extensions \
  python3-pip \
  git

echo "===== [4/6] AIライブラリ (YOLO) をインストール ====="
# CPU版 PyTorch (GPUが無くても動く) → ultralytics(YOLO)
pip3 install --user torch torchvision --index-url https://download.pytorch.org/whl/cpu
# ROS 2 Humble は numpy 1.x 前提なので 2.x にならないよう固定
pip3 install --user "numpy<2" "opencv-python-headless<4.11" ultralytics
# 重要: ultralytics が新しい setuptools を入れると colcon build が
#       "canonicalize_version() got an unexpected keyword argument" で失敗する。
#       ユーザー領域の setuptools を消して、Ubuntu 標準のものを使わせる。
pip3 uninstall -y setuptools 2>/dev/null || true
# 初回実行を速くするため、YOLOモデルを先にダウンロードしておく
mkdir -p ~/ros2_ws
(cd ~/ros2_ws && python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')") || true

echo "===== [5/6] 毎回の 'source' を自動化 (~/.bashrc に追記) ====="
grep -q "source /opt/ros/humble/setup.bash" ~/.bashrc || \
  echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
grep -q 'export PATH=$HOME/.local/bin' ~/.bashrc || \
  echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc

echo "===== [6/6] 確認 ====="
source /opt/ros/humble/setup.bash
echo "ROS_DISTRO = $ROS_DISTRO"
ign gazebo --versions || true
python3 -c "import ultralytics, numpy; print('ultralytics', ultralytics.__version__, '/ numpy', numpy.__version__)"

echo ""
echo "*** 完了! ターミナルを一度閉じて、開き直してください ***"
