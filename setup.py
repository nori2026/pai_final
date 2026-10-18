import os
from glob import glob
from setuptools import setup

package_name = 'pai_final'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # launch / worlds / config フォルダをインストール先にコピーする
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*.sdf')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_omnicampus_name',
    maintainer_email='noreply@example.com',
    description='PAI final assignment: YOLO person-following diff-drive robot in Gazebo',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'person_follower = pai_final.person_follower:main',
            'person_mover = pai_final.person_mover:main',
        ],
    },
)
