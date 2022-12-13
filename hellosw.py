import logging
import logging.handlers
import hashlib
import time
import sys
import pandas as pd
from functools import wraps
from netmiko import ConnectHandler
from pathlib import Path


CLEAN_FLAG = False    #清理相同配置文件标志
DELAY_FLAG = 1        #命令执行间隔时间基数
LOGFILE = 'hellosw.log'   #日志文件名


def initLogger(name=__name__):
	'''返回自定义的日志实例，同时在终端和文件（hellosw.log）中输出日志信息'''
	logger = logging.getLogger(name)
	logger.setLevel(logging.DEBUG)
	formatter = logging.Formatter('%(asctime)s-%(name)s-%(levelname)s-%(message)s')
	#设置终端窗口
	ch = logging.StreamHandler()
	ch.setLevel(logging.DEBUG)
	ch.setFormatter(formatter)
	logger.addHandler(ch)
	#设置日志文件,大小1M，最多保存10个文件
	rotating_handler = logging.handlers.RotatingFileHandler(LOGFILE, encoding='utf-8', maxBytes=1048576, backupCount=10)
	rotating_handler.setLevel(logging.INFO)
	rotating_handler.setFormatter(formatter)
	logger.addHandler(rotating_handler)
	#返回日志实例
	return logger

logger = initLogger()

def fileMd5(filename):
	'''返回文件的MD5码值'''
	size = 8192
	fmd5 = hashlib.md5()
	with open(filename, 'rb') as f:
		while True:
			data = f.read(size)
			if not data:
				break
			fmd5.update(data)
	logger.debug(f"文件 {Path(filename).name} 的MD5码: {fmd5.hexdigest()}")
	return fmd5.hexdigest()

def convert_time(seconds):
	'''把秒数转换为时、分、秒形式'''
	minutes, seconds = divmod(seconds, 60)
	hours, minutes = divmod(minutes, 60)
	return f"{hours}:{minutes}:{seconds}"

def run_times(func):
	'''装饰器，记录函数运行的时间'''
	dataformat = '%Y-%m-%d %H:%M:%S'  #日期的输出格式
	@wraps(func)
	def decorated(*args, **kwargs):
		t_start = time.time()
		logger.info('开始运行时间: {}'.format(time.strftime(dataformat, time.localtime(t_start))))
		func(*args, **kwargs)
		t_end = time.time()
		logger.info('结束运行时间: {}'.format(time.strftime(dataformat, time.localtime(t_end))))
		logger.info('总运行时间: {}'.format(convert_time(int(t_end-t_start))))
	return decorated

def loadSWinfo(filename):
	'''读取EXCEL文件，获取交换机的配置信息。 keys_must为文件的必须字段'''
	keys_must = ['host', 'device_type', 'username', 'password','command', 'enable', 'secret', 'timeout', 'conn_timeout', 'port']
	default_value = {'device_type': 'unknown', 'timeout': 100, 'conn_timeout': 10}
	logger.info(f"正在读取文件:{filename}")
	df = pd.read_excel(filename, skiprows=3, usecols=keys_must)  #跳过开头3行，读指定的列
	if df.empty:
		raise ValueError(f"配置文件中没有交换机信息，请检查文件: {filename}")
	df = df.fillna(value=default_value)    #填充默认值
	return df.to_dict(orient='records')

class BaseSwitch(object):
	'''连接交换机，获得command字段命令执行的结果'''
	def __init__(self, **kwargs):
		self._cmd = kwargs.pop('command')
		self._enable = kwargs.pop('enable')
		self._dev = kwargs
		self._IP = self._dev['host']
		self._cmd_type = self._getCmdType()
		self._cmd_result = None
		self._hostname = None
		self._conn_switch()


	@property
	def IP(self):
		'''返回设备的IP地址'''
		return self._IP

	@property
	def hostname(self):
		'''返回交换机的名称'''
		if self._hostname == None:
			raise ValueError(f"交换机配置信息hostname获取失败或不完整: {self._IP}")
		return self._hostname

	@property
	def cmdtype(self):
		return self._cmd_type

	@property
	def cmdresult(self):
		'''返回命令执行的结果'''
		if self._cmd_result == None:
			raise ValueError(f"交换机配置信息cmdresult获取失败或不完整: {self._IP}")
		return self._cmd_result


	def _conn_switch(self):
		'''连接交换机并执行命令'''
		with ConnectHandler(**self._dev) as conn:
			time.sleep(DELAY_FLAG)
			if self._enable:
				conn.enable()
			time.sleep(3*DELAY_FLAG)
			prompt = conn.find_prompt()
			logger.debug(f"交换机提示符: {prompt}")
			self._hostname = self._normalize_SW_name(prompt)   #需优化
			time.sleep(2*DELAY_FLAG)
			self._cmd_result = conn.send_command(self._cmd)
			#没有返回数据，重试三次，失败抛出异常
			i = 0
			while not self._cmd_result:
				if i>2:
					raise ValueError(f"交换机配置信息cmdresult获取失败或不完整")
				time.sleep(3*DELAY_FLAG)
				self._cmd_result = conn.send_command(self._cmd)
				i += 1
						

	def _normalize_SW_name(self, prompt):
		'''去除首尾的特定符号'''
		return prompt.strip('<>[]#')

	def _getCmdType(self):
		'''命令的类别'''
		cmd_type = {'dis cur': 'conf',
				'show run': 'conf',
				'dis ip routing-table': 'route',
				'show ip route': 'route'}
		return cmd_type.get(self._cmd, 'unknown')

class SWinfoSavePath(object):
	'''交换机配置信息的保存目录'''
	def __init__(self, save_path=None):
		self._save_path = Path(save_path) if save_path else Path.cwd()
		self._dirs = [entry for entry in self._save_path.iterdir() if entry.is_dir()]
		# logger.debug(f"包含的子目录: {self._dirs}")
		logger.debug(f"主目录 {self._save_path.name} 包含的子目录: {[f.name for f in self._dirs]}")

	def _nowtime(self):
		return time.strftime("%Y%m%d%H%M")    #当前时间的字符串形式

	def save(self, switch):
		'''保存交换机的信息'''
		subdir = Path(self._save_path, switch.hostname)
		logger.debug(f"子目录名: {subdir}")
		if not Path(subdir).exists():
			Path.mkdir(subdir)
			self._dirs.append(subdir)
			logger.debug(f"新建子目录: {subdir}")
		fname = f"{switch.IP}_{self._nowtime()}_{switch.cmdtype}.txt"
		logger.debug(f"配置信息文件名: {fname}")
		fpath = Path(subdir, fname)
		with open(fpath, mode='w', encoding='utf-8') as f:
			f.write(switch.cmdresult)
			logger.info(f"配置信息已保存至文件: {fpath}")


	def cleanSameFiles(self):
		for _dir in self._dirs:
			files = [f for f in Path(_dir).glob('*.txt')]
			logger.debug(f"目录 {_dir.name} 中的文件有: {files}")
			if not files:
				logger.debug(f"目录 {_dir} 为空")
				continue
			files.sort(key=lambda x: x.stat().st_mtime)  #按最近修改时间排序
			last_md5 = fileMd5(files.pop())
			for i in range(len(files)-1):
				f = files.pop()
				if fileMd5(f) == last_md5:
					logger.debug(f"删除重复文件: {f}")
					f.unlink()  #执行删除
				else:
					break

@run_times
def main(swfile, save_path=None):
	'''
	:param swfile: 存储交换机信息的EXCEL文件名
	:param save_path: 交换机配置信息保存的总目录
	:return: None
	'''
	if save_path:
		if not Path(save_path).exists():
			logger.error(f"目录 {save_path} 不存在，请检查")
			return
	if not Path(swfile).is_file():
		logger.error(f"交换机配置信息文件 {swfile} 不存在，请检查")
		return
	swPath = SWinfoSavePath(save_path)    #生成配置文件保存目录实例
	try:
		devs = loadSWinfo(swfile)             #读取交换机信息文件，获得交换机连接参数
	except Exception as e:
		logger.error(f"读交换机信息文件错误: {swfile} 错误原因: {e}")
		return
	for dev in devs:
		try:
			sw = BaseSwitch(**dev)         #连接交换机并获取信息
		except Exception as e:
			logger.error(f"连接交换机错误: {dev['host']}，错误原因: {e}")
			continue
		try:
			swPath.save(sw)                #保存交换机信息
		except Exception as e:
			logger.error(f"保存交换机的信息时出错: {dev['host']}，错误原因: {e}")
	try:
		if CLEAN_FLAG:		
			swPath.cleanSameFiles()   #清除目录中的相同交换机配置文件
	except Exception as e:
		logger.error(f"清理重复文件时错误: {e}")



if __name__ == '__main__':
	'''
	命令行可带参数
	第一个参数：保存交换机信息的文件名
	第二个参数：保存交换机配置的目录
	'''
	fn = sys.argv[1] if len(sys.argv) >= 2 else r'switch_info.xlsx'
	fp = sys.argv[2] if len(sys.argv) >= 3 else Path.cwd()
	# print(f"fname= {fn}, fpath= {fp}")
	main(fn, fp)
