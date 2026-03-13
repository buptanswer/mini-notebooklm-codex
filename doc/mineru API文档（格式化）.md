> 单个文件解析

### 创建解析任务[​](#创建解析任务 "Direct link to 创建解析任务")

#### 接口说明[​](#接口说明 "Direct link to 接口说明")

适用于通过 API 创建解析任务的场景，用户须先申请 Token。 注意：

*   单个文件大小不能超过 200MB, 文件页数不超出 600 页
*   每个账号每天享有 2000 页最高优先级解析额度，超过 2000 页的部分优先级降低
*   因网络限制，github、aws 等国外 URL 会请求超时
*   该接口不支持文件直接上传
*   header 头中需要包含 Authorization 字段，格式为 Bearer + 空格 + Token

#### Python 请求示例（适用于 pdf、doc、ppt、图片文件）：[​](#python-请求示例适用于pdfdocppt图片文件 "Direct link to Python 请求示例（适用于pdf、doc、ppt、图片文件）：")

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}

res = requests.post(url,headers=header,json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])


```

#### Python 请求示例（适用于 html 文件）：[​](#python-请求示例适用于html文件 "Direct link to Python 请求示例（适用于html文件）：")

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "url": "https://****",
    "model_version": "MinerU-HTML"
}

res = requests.post(url,headers=header,json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])


```

#### CURL 请求示例（适用于 pdf、doc、ppt、图片文件）：[​](#curl-请求示例适用于pdfdocppt图片文件 "Direct link to CURL 请求示例（适用于pdf、doc、ppt、图片文件）：")

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}'


```

#### CURL 请求示例（适用于 html 文件）：[​](#curl-请求示例适用于html文件 "Direct link to CURL 请求示例（适用于html文件）：")

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "url": "https://****",
    "model_version": "MinerU-HTML"
}'


```

#### 请求体参数说明[​](#请求体参数说明 "Direct link to 请求体参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>是否必选</th><th>示例</th><th>描述</th></tr></thead><tbody><tr><td>url</td><td>string</td><td>是</td><td><a href="https://cdn-mineru.openxlab.org.cn/demo/example.pdf" target="_blank" rel="noopener noreferrer">https://static.openxlab.org.cn/<br>opendatalab/pdf/demo.pdf</a></td><td>文件 URL，支持. pdf、.doc、.docx、.ppt、.pptx、.png、.jpg、.jpeg、.html 多种格式</td></tr><tr><td>is_ocr</td><td>bool</td><td>否</td><td>false</td><td>是否启动 ocr 功能，默认 false，仅对 pipeline、vlm 模型有效</td></tr><tr><td>enable_formula</td><td>bool</td><td>否</td><td>true</td><td>是否开启公式识别，默认 true，仅对 pipeline、vlm 模型有效。特别注意的是：对于 vlm 模型，这个参数指只会影响行内公式的解析</td></tr><tr><td>enable_table</td><td>bool</td><td>否</td><td>true</td><td>是否开启表格识别，默认 true，仅对 pipeline、vlm 模型有效</td></tr><tr><td>language</td><td>string</td><td>否</td><td>ch</td><td>指定文档语言，默认 ch，其他可选值列表详见：<a href="https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3" target="_blank"></a><a href="https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3" target="_blank" rel="noopener noreferrer">https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3</a>，仅对 pipeline、vlm 模型有效</td></tr><tr><td>data_id</td><td>string</td><td>否</td><td>abc**</td><td>解析对象对应的数据 ID。由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成，不超过 128 个字符，可以用于唯一标识您的业务数据。</td></tr><tr><td>callback</td><td>string</td><td>否</td><td><a href="http://127.0.0.1/callback" target="_blank" rel="noopener noreferrer">http://127.0.0.1/callback</a></td><td>解析结果回调通知您的 URL，支持使用 HTTP 和 HTTPS 协议的地址。该字段为空时，您必须定时轮询解析结果。callback 接口必须支持 POST 方法、UTF-8 编码、Content-Type:application/json 传输数据，以及参数 checksum 和 content。解析接口按照以下规则和格式设置 checksum 和 content，调用您的 callback 接口返回检测结果。<br>checksum：字符串格式，由用户 uid + seed + content 拼成字符串，通过 SHA256 算法生成。用户 UID，可在个人中心查询。为防篡改，您可以在获取到推送结果时，按上述算法生成字符串，与 checksum 做一次校验。<br>content：JSON 字符串格式，请自行解析反转成 JSON 对象。关于 content 结果的示例，请参见任务查询结果的返回示例，对应任务查询结果的 data 部分。<br>说明: 您的服务端 callback 接口收到 Mineru 解析服务推送的结果后，如果返回的 HTTP 状态码为 200，则表示接收成功，其他的 HTTP 状态码均视为接收失败。接收失败时，mineru 将最多重复推送 5 次检测结果，直到接收成功。重复推送 5 次后仍未接收成功，则不再推送，建议您检查 callback 接口的状态。</td></tr><tr><td>seed</td><td>string</td><td>否</td><td>abc**</td><td>随机字符串，该值用于回调通知请求中的签名。由英文字母、数字、下划线（_）组成，不超过 64 个字符，由您自定义。用于在接收到内容安全的回调通知时校验请求由 Mineru 解析服务发起。<br>说明：当使用 callback 时，该字段必须提供。</td></tr><tr><td>extra_formats</td><td>[string]</td><td>否</td><td>["docx","html"]</td><td>markdown、json 为默认导出格式，无须设置，该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。</td></tr><tr><td>page_ranges</td><td>string</td><td>否</td><td>1-600</td><td>指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第 2 页、第 4 页至第 6 页（包含 4 和 6，结果为 [2,4,5,6]）；"2--2"：表示从第 2 页一直选取到倒数第二页（其中 "-2" 表示倒数第二页）。</td></tr><tr><td>model_version</td><td>string</td><td>否</td><td>vlm</td><td>mineru 模型版本，三个选项: pipeline、vlm、MinerU-HTML，默认 pipeline。如果解析的是 HTML 文件，model_version 需明确指定为 MineruU-HTML，如果是非 HTML 文件，可选择 pipeline 或 vlm</td></tr><tr><td>no_cache</td><td>bool</td><td>否</td><td>false</td><td>是否绕过缓存，默认 false。我们的 API 服务器会将 URL 内容缓存一段时间，设置为 true 可忽略缓存结果，从 URL 获取最新内容。</td></tr><tr><td>cache_tolerance</td><td>int</td><td>否</td><td>900</td><td>缓存容忍时间（秒），默认 900（15 分钟）。 可容忍的 URL 内容缓存有效时间，超出该时间的缓存不会被使用。当 no_cache 为 false 时有效</td></tr></tbody></table>

#### 响应参数说明[​](#响应参数说明 "Direct link to 响应参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>a90e6ab6-44f3-4554-b459-b62fe4c6b436</td><td>提取任务 id，可用于查询任务结果</td></tr></tbody></table>

#### 响应示例[​](#响应示例 "Direct link to 响应示例")

```
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b4***"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}


```

### 获取任务结果[​](#获取任务结果 "Direct link to 获取任务结果")

#### 接口说明[​](#接口说明-1 "Direct link to 接口说明")

通过 task_id 查询提取任务目前的进度，任务处理完成后，接口会响应对应的提取详情。

#### Python 请求示例[​](#python-请求示例 "Direct link to Python 请求示例")

```
import requests

token = "官网申请的api token"
url = f"https://mineru.net/api/v4/extract/task/{task_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
print(res.json()["data"])


```

#### CURL 请求示例[​](#curl-请求示例 "Direct link to CURL 请求示例")

```
curl --location --request GET 'https://mineru.net/api/v4/extract/task/{task_id}' \
--header 'Authorization: Bearer *****' \
--header 'Accept: */*'


```

#### 响应参数说明[​](#响应参数说明-1 "Direct link to 响应参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.task_id</td><td>string</td><td>abc**</td><td>任务 ID</td></tr><tr><td>data.data_id</td><td>string</td><td>abc**</td><td>解析对象对应的数据 ID。<br>说明：如果在解析请求参数中传入了 data_id，则此处返回对应的 data_id。</td></tr><tr><td>data.state</td><td>string</td><td>done</td><td>任务处理状态，完成: done，pending: 排队中，running: 正在解析，failed：解析失败，converting：格式转换中</td></tr><tr><td>data.full_zip_url</td><td>string</td><td><a href="https://cdn-mineru.openxlab.org.cn/" target="_blank" rel="noopener noreferrer">https://cdn-mineru.openxlab.org.cn/</a><br>pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip</td><td>文件解析结果压缩包<br>非 html 文件解析结果详细说明请参考：<a href="https://opendatalab.github.io/MinerU/reference/output_files/" target="_blank" rel="noopener noreferrer">https://opendatalab.github.io/MinerU/reference/output_files/</a> ，其中 layout.json 对应中间处理结果 (middle.json), **_model.json 对应模型推理结果 (model.json)，**_content_list.json 对应内容列表 (content_list.json)，full.md 为 MarkDown 解析结果。<p>html 文件解析结果略有不同：full.md 为 MarkDown 解析结果, main.html 为提取后正文 html</p></td></tr><tr><td>data.err_msg</td><td>string</td><td>文件格式不支持，请上传符合要求的文件类型</td><td>解析失败原因，当 state=failed 时有效</td></tr><tr><td>data.extract_progress.extracted_pages</td><td>int</td><td>1</td><td>文档已解析页数，当 state=running 时有效</td></tr><tr><td>data.extract_progress.start_time</td><td>string</td><td>2025-01-20 11:43:20</td><td>文档解析开始时间，当 state=running 时有效</td></tr><tr><td>data.extract_progress.total_pages</td><td>int</td><td>2</td><td>文档总页数，当 state=running 时有效</td></tr></tbody></table>

#### 响应示例[​](#响应示例-1 "Direct link to 响应示例")

```
{
  "code": 0,
  "data": {
    "task_id": "47726b6e-46ca-4bb9-******",
    "state": "running",
    "err_msg": "",
    "extract_progress": {
      "extracted_pages": 1,
      "total_pages": 2,
      "start_time": "2025-01-20 11:43:20"
    }
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}


```

```
{
  "code": 0,
  "data": {
    "task_id": "47726b6e-46ca-4bb9-******",
    "state": "done",
    "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip",
    "err_msg": ""
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}


```

批量文件解析[​](#批量文件解析 "Direct link to 批量文件解析")
------------------------------------------

### 文件批量上传解析[​](#文件批量上传解析 "Direct link to 文件批量上传解析")

#### 接口说明[​](#接口说明-2 "Direct link to 接口说明")

适用于本地文件上传解析的场景，可通过此接口批量申请文件上传链接，上传文件后，系统会自动提交解析任务 注意：

*   申请的文件上传链接有效期为 24 小时，请在有效期内完成文件上传
*   上传文件时，无须设置 Content-Type 请求头
*   文件上传完成后，无须调用提交解析任务接口。系统会自动扫描已上传完成文件自动提交解析任务
*   单次申请链接不能超过 200 个
*   header 头中需要包含 Authorization 字段，格式为 Bearer + 空格 + Token

#### Python 请求示例（适用于 pdf、doc、ppt、图片文件）：[​](#python-请求示例适用于pdfdocppt图片文件-1 "Direct link to Python 请求示例（适用于pdf、doc、ppt、图片文件）：")

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/file-urls/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version":"vlm"
}
file_path = ["demo.pdf"]
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]
            print('batch_id:{},urls:{}'.format(batch_id, urls))
            for i in range(0, len(urls)):
                with open(file_path[i], 'rb') as f:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"{urls[i]} upload success")
                    else:
                        print(f"{urls[i]} upload failed")
        else:
            print('apply upload url failed,reason:{}'.format(result.msg))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)


```

#### Python 请求示例（适用于 html 文件）：[​](#python-请求示例适用于html文件-1 "Direct link to Python 请求示例（适用于html文件）：")

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/file-urls/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"name":"demo.html", "data_id": "abcd"}
    ],
    "model_version":"MinerU-HTML"
}
file_path = ["demo.html"]
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]
            print('batch_id:{},urls:{}'.format(batch_id, urls))
            for i in range(0, len(urls)):
                with open(file_path[i], 'rb') as f:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"{urls[i]} upload success")
                    else:
                        print(f"{urls[i]} upload failed")
        else:
            print('apply upload url failed,reason:{}'.format(result.msg))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)


```

#### CURL 请求示例（适用于 pdf、doc、ppt、图片文件）：[​](#curl-请求示例适用于pdfdocppt图片文件-1 "Direct link to CURL 请求示例（适用于pdf、doc、ppt、图片文件）：")

```
curl --location --request POST 'https://mineru.net/api/v4/file-urls/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}'


```

#### CURL 请求示例（适用于 html 文件）：[​](#curl-请求示例适用于html文件-1 "Direct link to CURL 请求示例（适用于html文件）：")

```
curl --location --request POST 'https://mineru.net/api/v4/file-urls/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"name":"demo.html", "data_id": "abcd"}
    ],
    "model_version": "MinerU-HTML"
}'


```

#### CURL 文件上传示例：[​](#curl-文件上传示例 "Direct link to CURL 文件上传示例：")

```
curl -X PUT -T /path/to/your/file.pdf 'https://****'


```

#### 请求体参数说明[​](#请求体参数说明-1 "Direct link to 请求体参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>是否必选</th><th>示例</th><th>描述</th></tr></thead><tbody><tr><td>enable_formula</td><td>bool</td><td>否</td><td>true</td><td>是否开启公式识别，默认 true，仅对 pipeline、vlm 模型有效。特别注意的是：对于 vlm 模型，这个参数指只会影响行内公式的解析</td></tr><tr><td>enable_table</td><td>bool</td><td>否</td><td>true</td><td>是否开启表格识别，默认 true，仅对 pipeline、vlm 模型有效</td></tr><tr><td>language</td><td>string</td><td>否</td><td>ch</td><td>指定文档语言，默认 ch，其他可选值列表详见：<a href="https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3" target="_blank"></a><a href="https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3" target="_blank" rel="noopener noreferrer">https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3</a>，仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.‌name</td><td>string</td><td>是</td><td>demo.pdf</td><td>文件名，支持. pdf、.doc、.docx、.ppt、.pptx、.png、.jpg、.jpeg、.html 多种格式，我们强烈建议文件名带上正确的后缀名</td></tr><tr><td>file.is_ocr</td><td>bool</td><td>否</td><td>true</td><td>是否启动 ocr 功能，默认 false，仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.data_id</td><td>string</td><td>否</td><td>abc**</td><td>解析对象对应的数据 ID。由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成，不超过 128 个字符，可以用于唯一标识您的业务数据。</td></tr><tr><td>file.page_ranges</td><td>string</td><td>否</td><td>1-600</td><td>指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第 2 页、第 4 页至第 6 页（包含 4 和 6，结果为 [2,4,5,6]）；"2--2"：表示从第 2 页一直选取到倒数第二页（其中 "-2" 表示倒数第二页）。</td></tr><tr><td>callback</td><td>string</td><td>否</td><td><a href="http://127.0.0.1/callback" target="_blank" rel="noopener noreferrer">http://127.0.0.1/callback</a></td><td>解析结果回调通知您的 URL，支持使用 HTTP 和 HTTPS 协议的地址。该字段为空时，您必须定时轮询解析结果。callback 接口必须支持 POST 方法、UTF-8 编码、Content-Type:application/json 传输数据，以及参数 checksum 和 content。解析接口按照以下规则和格式设置 checksum 和 content，调用您的 callback 接口返回检测结果。<br>checksum：字符串格式，由用户 uid + seed + content 拼成字符串，通过 SHA256 算法生成。用户 UID，可在个人中心查询。为防篡改，您可以在获取到推送结果时，按上述算法生成字符串，与 checksum 做一次校验。<br>content：JSON 字符串格式，请自行解析反转成 JSON 对象。关于 content 结果的示例，请参见任务查询结果的返回示例，对应任务查询结果的 data 部分。<br>说明: 您的服务端 callback 接口收到 Mineru 解析服务推送的结果后，如果返回的 HTTP 状态码为 200，则表示接收成功，其他的 HTTP 状态码均视为接收失败。接收失败时，mineru 将最多重复推送 5 次检测结果，直到接收成功。重复推送 5 次后仍未接收成功，则不再推送，建议您检查 callback 接口的状态。</td></tr><tr><td>seed</td><td>string</td><td>否</td><td>abc**</td><td>随机字符串，该值用于回调通知请求中的签名。由英文字母、数字、下划线（_）组成，不超过 64 个字符。由您自定义，用于在接收到内容安全的回调通知时校验请求由 Mineru 解析服务发起。<br>说明: 当使用 callback 时，该字段必须提供。</td></tr><tr><td>extra_formats</td><td>[string]</td><td>否</td><td>["docx","html"]</td><td>markdown、json 为默认导出格式，无须设置，该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。</td></tr><tr><td>model_version</td><td>string</td><td>否</td><td>vlm</td><td>mineru 模型版本，三个选项: pipeline、vlm、MinerU-HTML，默认 pipeline。如果解析的是 HTML 文件，model_version 需明确指定为 MineruU-HTML，如果是非 HTML 文件，可选择 pipeline 或 vlm</td></tr></tbody></table>

#### 响应参数说明[​](#响应参数说明-2 "Direct link to 响应参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功： 0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.batch_id</td><td>string</td><td>2bb2f0ec-a336-4a0a-b61a-****</td><td>批量提取任务 id，可用于批量查询解析结果</td></tr><tr><td>data.files</td><td>[string]</td><td>["<a href="https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/***" target="_blank" rel="noopener noreferrer">https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/***</a>"]</td><td>文件上传链接</td></tr></tbody></table>

#### 响应示例[​](#响应示例-2 "Direct link to 响应示例")

```
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
    "file_urls": [
        "https://***"
    ]
  }
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}


```

### url 批量上传解析[​](#url-批量上传解析 "Direct link to url 批量上传解析")

#### 接口说明[​](#接口说明-3 "Direct link to 接口说明")

适用于通过 API 批量创建提取任务的场景 注意：

*   单次申请链接不能超过 200 个
*   文件大小不能超过 200MB, 文件页数不超出 600 页
*   因网络限制，github、aws 等国外 URL 会请求超时
*   header 头中需要包含 Authorization 字段，格式为 Bearer + 空格 + Token

#### Python 请求示例（适用于 pdf、doc、ppt、图片文件）：[​](#python-请求示例适用于pdfdocppt图片文件-2 "Direct link to Python 请求示例（适用于pdf、doc、ppt、图片文件）：")

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            print('batch_id:{}'.format(batch_id))
        else:
            print('submit task failed,reason:{}'.format(result.msg))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)


```

#### Python 请求示例（适用于 html 文件）：[​](#python-请求示例适用于html文件-2 "Direct link to Python 请求示例（适用于html文件）：")

```
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"url":"https://***", "data_id": "abcd"}
    ],
    "model_version": "MinerU-HTML"
}
try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            print('batch_id:{}'.format(batch_id))
        else:
            print('submit task failed,reason:{}'.format(result.msg))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)


```

#### CURL 请求示例（适用于 pdf、doc、ppt、图片文件）：[​](#curl-请求示例适用于pdfdocppt图片文件-2 "Direct link to CURL 请求示例（适用于pdf、doc、ppt、图片文件）：")

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}'


```

#### CURL 请求示例（适用于 html 文件）：[​](#curl-请求示例适用于html文件-2 "Direct link to CURL 请求示例（适用于html文件）：")

```
curl --location --request POST 'https://mineru.net/api/v4/extract/task/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"url":"https://***", "data_id": "abcd"}
    ],
    "model_version": "MinerU-HTML"
}'


```

#### 请求体参数说明[​](#请求体参数说明-2 "Direct link to 请求体参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>是否必选</th><th>示例</th><th>描述</th></tr></thead><tbody><tr><td>enable_formula</td><td>bool</td><td>否</td><td>true</td><td>是否开启公式识别，默认 true，仅对 pipeline、vlm 模型有效。特别注意的是：对于 vlm 模型，这个参数指只会影响行内公式的解析</td></tr><tr><td>enable_table</td><td>bool</td><td>否</td><td>true</td><td>是否开启表格识别，默认 true，仅对 pipeline、vlm 模型有效</td></tr><tr><td>language</td><td>string</td><td>否</td><td>ch</td><td>指定文档语言，默认 ch，其他可选值列表详见：<a href="https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3" target="_blank"></a><a href="https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3" target="_blank" rel="noopener noreferrer">https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3</a>，仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.url</td><td>string</td><td>是</td><td><a href="https://cdn-mineru.openxlab.org.cn/demo/example.pdf" target="_blank" rel="noopener noreferrer">demo.pdf</a></td><td>文件链接，支持. pdf、.doc、.docx、.ppt、.pptx、.png、.jpg、.jpeg、.html 多种格式</td></tr><tr><td>file.is_ocr</td><td>bool</td><td>否</td><td>true</td><td>是否启动 ocr 功能，默认 false，仅对 pipeline、vlm 模型有效</td></tr><tr><td>file.data_id</td><td>string</td><td>否</td><td>abc**</td><td>解析对象对应的数据 ID。由大小写英文字母、数字、下划线（_）、短划线（-）、英文句号（.）组成，不超过 128 个字符，可以用于唯一标识您的业务数据。</td></tr><tr><td>file.page_ranges</td><td>string</td><td>否</td><td>1-600</td><td>指定页码范围，格式为逗号分隔的字符串。例如："2,4-6"：表示选取第 2 页、第 4 页至第 6 页（包含 4 和 6，结果为 [2,4,5,6]）；"2--2"：表示从第 2 页一直选取到倒数第二页（其中 "-2" 表示倒数第二页）。</td></tr><tr><td>callback</td><td>string</td><td>否</td><td><a href="http://127.0.0.1/callback" target="_blank" rel="noopener noreferrer">http://127.0.0.1/callback</a></td><td>解析结果回调通知您的 URL，支持使用 HTTP 和 HTTPS 协议的地址。该字段为空时，您必须定时轮询解析结果。callback 接口必须支持 POST 方法、UTF-8 编码、Content-Type:application/json 传输数据，以及参数 checksum 和 content。解析接口按照以下规则和格式设置 checksum 和 content，调用您的 callback 接口返回检测结果。<br>checksum：字符串格式，由用户 uid + seed + content 拼成字符串，通过 SHA256 算法生成。用户 UID，可在个人中心查询。为防篡改，您可以在获取到推送结果时，按上述算法生成字符串，与 checksum 做一次校验。<br>content：JSON 字符串格式，请自行解析反转成 JSON 对象。关于 content 结果的示例，请参见任务查询结果的返回示例，对应任务查询结果的 data 部分。<br>说明: 您的服务端 callback 接口收到 Mineru 解析服务推送的结果后，如果返回的 HTTP 状态码为 200，则表示接收成功，其他的 HTTP 状态码均视为接收失败。接收失败时，mineru 将最多重复推送 5 次检测结果，直到接收成功。重复推送 5 次后仍未接收成功，则不再推送，建议您检查 callback 接口的状态。</td></tr><tr><td>seed</td><td>string</td><td>否</td><td>abc**</td><td>随机字符串，该值用于回调通知请求中的签名。由英文字母、数字、下划线（_）组成，不超过 64 个字符。由您自定义，用于在接收到内容安全的回调通知时校验请求由 Mineru 解析服务发起。<br>说明：当使用 callback 时，该字段必须提供。</td></tr><tr><td>extra_formats</td><td>[string]</td><td>否</td><td>["docx","html"]</td><td>markdown、json 为默认导出格式，无须设置，该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。</td></tr><tr><td>model_version</td><td>string</td><td>否</td><td>vlm</td><td>mineru 模型版本，三个选项: pipeline、vlm、MinerU-HTML，默认 pipeline。如果解析的是 HTML 文件，model_version 需明确指定为 MineruU-HTML，如果是非 HTML 文件，可选择 pipeline 或 vlm</td></tr><tr><td>no_cache</td><td>bool</td><td>否</td><td>false</td><td>是否绕过缓存，默认 false。我们的 API 服务器会将 URL 内容缓存一段时间，设置为 true 可忽略缓存结果，从 URL 获取最新内容。</td></tr><tr><td>cache_tolerance</td><td>int</td><td>否</td><td>900</td><td>缓存容忍时间（秒），默认 900（15 分钟）。 可容忍的 URL 内容缓存有效时间，超出该时间的缓存不会被使用。当 no_cache 为 false 时有效</td></tr></tbody></table>

#### 请求体示例[​](#请求体示例 "Direct link to 请求体示例")

```
{
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}


```

#### 响应参数说明[​](#响应参数说明-3 "Direct link to 响应参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.batch_id</td><td>string</td><td>2bb2f0ec-a336-4a0a-b61a-****</td><td>批量提取任务 id，可用于批量查询解析结果</td></tr></tbody></table>

#### 响应示例[​](#响应示例-3 "Direct link to 响应示例")

```
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}


```

### 批量获取任务结果[​](#批量获取任务结果 "Direct link to 批量获取任务结果")

#### 接口说明[​](#接口说明-4 "Direct link to 接口说明")

通过 batch_id 批量查询提取任务的进度。

#### Python 请求示例[​](#python-请求示例-1 "Direct link to Python 请求示例")

```
import requests

token = "官网申请的api token"
url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
print(res.json()["data"])


```

#### CURL 请求示例[​](#curl-请求示例-1 "Direct link to CURL 请求示例")

```
curl --location --request GET 'https://mineru.net/api/v4/extract-results/batch/{batch_id}' \
--header 'Authorization: Bearer *****' \
--header 'Accept: */*'


```

#### 响应参数说明[​](#响应参数说明-4 "Direct link to 响应参数说明")

<table><thead><tr><th>参数</th><th>类型</th><th>示例</th><th>说明</th></tr></thead><tbody><tr><td>code</td><td>int</td><td>0</td><td>接口状态码，成功：0</td></tr><tr><td>msg</td><td>string</td><td>ok</td><td>接口处理信息，成功："ok"</td></tr><tr><td>trace_id</td><td>string</td><td>c876cd60b202f2396de1f9e39a1b0172</td><td>请求 ID</td></tr><tr><td>data.batch_id</td><td>string</td><td>2bb2f0ec-a336-4a0a-b61a-241afaf9cc87</td><td>batch_id</td></tr><tr><td>data.extract_result.file_name</td><td>string</td><td>demo.pdf</td><td>文件名</td></tr><tr><td>data.extract_result.state</td><td>string</td><td>done</td><td>任务处理状态，完成: done，waiting-file: 等待文件上传排队提交解析任务中，pending: 排队中，running: 正在解析，failed：解析失败，converting：格式转换中</td></tr><tr><td>data.extract_result.full_zip_url</td><td>string</td><td><a href="https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip" target="_blank" rel="noopener noreferrer">https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip</a></td><td>文件解析结果压缩包<br>非 html 文件解析结果详细说明请参考：<a href="https://opendatalab.github.io/MinerU/reference/output_files/" target="_blank" rel="noopener noreferrer">https://opendatalab.github.io/MinerU/reference/output_files/</a> ，其中 layout.json 对应中间处理结果 (middle.json), **_model.json 对应模型推理结果 (model.json)，**_content_list.json 对应内容列表 (content_list.json)，full.md 为 MarkDown 解析结果。<p>html 文件解析结果略有不同：full.md 为 MarkDown 解析结果, main.html 为提取后正文 html</p></td></tr><tr><td>data.extract_result.err_msg</td><td>string</td><td>文件格式不支持，请上传符合要求的文件类型</td><td>解析失败原因，当 state=failed 时，有效</td></tr><tr><td>data.extract_result.data_id</td><td>string</td><td>abc**</td><td>解析对象对应的数据 ID。<br>说明：如果在解析请求参数中传入了 data_id，则此处返回对应的 data_id。</td></tr><tr><td>data.extract_result.extract_progress.extracted_pages</td><td>int</td><td>1</td><td>文档已解析页数，当 state=running 时有效</td></tr><tr><td>data.extract_result.extract_progress.start_time</td><td>string</td><td>2025-01-20 11:43:20</td><td>文档解析开始时间，当 state=running 时有效</td></tr><tr><td>data.extract_result.extract_progress.total_pages</td><td>int</td><td>2</td><td>文档总页数，当 state=running 时有效</td></tr></tbody></table>

#### 响应示例[​](#响应示例-4 "Direct link to 响应示例")

```
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
    "extract_result": [
      {
        "file_name": "example.pdf",
        "state": "done",
        "err_msg": "",
        "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip"
      },
      {
        "file_name":"demo.pdf",
        "state": "running",
        "err_msg": "",
        "extract_progress": {
          "extracted_pages": 1,
          "total_pages": 2,
          "start_time": "2025-01-20 11:43:20"
        }
      }
    ]
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}


```

### 常见错误码[​](#常见错误码 "Direct link to 常见错误码")

<table><thead><tr><th>错误码</th><th>说明</th><th>解决建议</th></tr></thead><tbody><tr><td>A0202</td><td>Token 错误</td><td>检查 Token 是否正确，请检查是否有 Bearer 前缀 或者更换新 Token</td></tr><tr><td>A0211</td><td>Token 过期</td><td>更换新 Token</td></tr><tr><td>-500</td><td>传参错误</td><td>请确保参数类型及 Content-Type 正确</td></tr><tr><td>-10001</td><td>服务异常</td><td>请稍后再试</td></tr><tr><td>-10002</td><td>请求参数错误</td><td>检查请求参数格式</td></tr><tr><td>-60001</td><td>生成上传 URL 失败，请稍后再试</td><td>请稍后再试</td></tr><tr><td>-60002</td><td>获取匹配的文件格式失败</td><td>检测文件类型失败，请求的文件名及链接中带有正确的后缀名，且文件为 pdf,doc,docx,ppt,pptx,png,jp(e)g 中的一种</td></tr><tr><td>-60003</td><td>文件读取失败</td><td>请检查文件是否损坏并重新上传</td></tr><tr><td>-60004</td><td>空文件</td><td>请上传有效文件</td></tr><tr><td>-60005</td><td>文件大小超出限制</td><td>检查文件大小，最大支持 200MB</td></tr><tr><td>-60006</td><td>文件页数超过限制</td><td>请拆分文件后重试</td></tr><tr><td>-60007</td><td>模型服务暂时不可用</td><td>请稍后重试或联系技术支持</td></tr><tr><td>-60008</td><td>文件读取超时</td><td>检查 URL 可访问</td></tr><tr><td>-60009</td><td>任务提交队列已满</td><td>请稍后再试</td></tr><tr><td>-60010</td><td>解析失败</td><td>请稍后再试</td></tr><tr><td>-60011</td><td>获取有效文件失败</td><td>请确保文件已上传</td></tr><tr><td>-60012</td><td>找不到任务</td><td>请确保 task_id 有效且未删除</td></tr><tr><td>-60013</td><td>没有权限访问该任务</td><td>只能访问自己提交的任务</td></tr><tr><td>-60014</td><td>删除运行中的任务</td><td>运行中的任务暂不支持删除</td></tr><tr><td>-60015</td><td>文件转换失败</td><td>可以手动转为 pdf 再上传</td></tr><tr><td>-60016</td><td>文件转换失败</td><td>文件转换为指定格式失败，可以尝试其他格式导出或重试</td></tr><tr><td>-60017</td><td>重试次数达到上线</td><td>等后续模型升级后重试</td></tr><tr><td>-60018</td><td>每日解析任务数量已达上限</td><td>明日再来</td></tr><tr><td>-60019</td><td>html 文件解析额度不足</td><td>明日再来</td></tr><tr><td>-60020</td><td>文件拆分失败</td><td>请稍后重试</td></tr><tr><td>-60021</td><td>读取文件页数失败</td><td>请稍后重试</td></tr><tr><td>-60022</td><td>网页读取失败</td><td>可能因网络问题或者限频导致读取失败，请稍后重试</td></tr></tbody></table>