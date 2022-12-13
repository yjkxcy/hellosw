# hellosw
批量获取并保存交换机配置信息

程序在如下环境中运行测试正常： <br> 
Python 3.10.0 <br> 
netmiko-4.1.0 <br> 
 <br> 
在一个EXCEL文件中保存交换机的连接信息，程序自动读取并连接到交换机，执行command字段的命令， <br> 
然后保存命令执行的结果。目录名是交换机的hostname，文件名由IP、备份时间组成 <br> 
 <br> 
EXCEL文件格式说明： <br> 
1、必须包含的字段：'host', 'device_type', 'username', 'password','command', 'enable', <br> 
  'secret', 'timeout', 'conn_timeout', 'port' <br> 
2、前三行是说明信息，不得删除或添加行数（会影响文件的正常读取） <br> 
3、测试通过的命令   Huawei H3C: dis cur、dis ip routing-table <br> 
                  Cisco Ruijie: show run、show ip route <br> 
4、必填字段  'host', 'device_type', 'username', 'password','command', 'enable' <br> 
  其他字段根据需要填写，如未填写程序会设置默认值 <br> 
5、默认EXCEL文件和程序执行文件在同一目录下 <br> 
