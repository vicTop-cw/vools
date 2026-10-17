"""本机 Spark 2.4.3 启动前置修复（环境问题，非代码问题）。

本机默认环境有三处不匹配，导致 pyspark 2.4.3 无法启动：
1. JAVA_HOME 指向 JDK 17 —— Spark 2.4 只支持 Java 8，会报
   Py4JError: PythonUtils.getEncryptionEnabled does not exist in the JVM
2. SPARK_HOME 指向 Spark 3.5 的发行包，而 venv 里装的是 pyspark 2.4.3 ——
   Python 侧 2.4 的代码去驱动 3.5 的 jar，类名对不上
3. Windows 缺 winutils.exe（HADOOP_HOME 未设）

导入本模块即完成修复（须在 import pyspark 之前）。
"""
import os
import sys

JDK8 = r'E:\Java\jdk8'
HADOOP = r'E:\Tools\hadoop'

if os.path.isdir(JDK8):
    os.environ['JAVA_HOME'] = JDK8
    os.environ['PATH'] = os.path.join(JDK8, 'bin') + os.pathsep + os.environ.get('PATH', '')

# 清掉指向 Spark 3.5 的 SPARK_HOME，让 pyspark 用自己的 jars
os.environ.pop('SPARK_HOME', None)
os.environ.pop('SPARK_CONF_DIR', None)

if os.path.isdir(HADOOP):
    os.environ['HADOOP_HOME'] = HADOOP
    os.environ['PATH'] = os.path.join(HADOOP, 'bin') + os.pathsep + os.environ.get('PATH', '')

os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable
os.environ.setdefault('SPARK_LOCAL_IP', '127.0.0.1')
