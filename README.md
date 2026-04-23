## 功能
1. 每天爬取SkyperfecTV官网的EPG数据。
2. 下载最近48小时内的节目预告图片，并重命名为Fury Skin可以识别的格式（例如：2158f4936564_1775401200），其中前面可以说是Fury对频道的识别码（不同机器可能不同），后面是unix时间戳。
3. 本脚本对图片进行了毛玻璃处理，使其尽量适配Fury海报比例。
4. 对最终图片进行硬链接（HardLink），减小占用空间。
5. 优化缓存处理机制，自动删除过期缓存。
6. 由于官网节目会有变动，不能保证100%准确。
   
## 下载链接
1. EPG  
 https://github.com/mathlabroom/SKyperfectv-EPG-/releases/download/latest/epg_ultimate.xml
 https://github.com/mathlabroom/SKyperfectv-EPG-/releases/download/latest/epg_ultimate.xml.gz
2. Posters  海报  
 https://github.com/mathlabroom/SKyperfectv-EPG-/releases/download/latest/fury_posters.zip
 https://github.com/mathlabroom/SKyperfectv-EPG-/releases/download/latest/fury_posters.tar.gz

## 效果图
<img width="960" height="540" alt="image" src="https://github.com/user-attachments/assets/12185c41-aa54-41b0-a3f9-8063a1dbc868" />
<img width="960" height="540" alt="image" src="https://github.com/user-attachments/assets/64714ff7-5122-40c9-b1cc-acf7051d29a4" />
