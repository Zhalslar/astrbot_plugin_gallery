import base64
import httpx

ACCESS_TOKEN = ""


async def ocr(img: bytes) -> str | None:
    img_base64 = base64.b64encode(img).decode("utf-8")
    access_token = ACCESS_TOKEN
    request_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token={access_token}"
    params = {"image": img_base64}
    headers = {"content-type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(request_url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            words_list = [item["words"] for item in data["words_result"]]
            result_string = "\n".join(words_list)
            return result_string
        except httpx.HTTPStatusError as e:
            print(
                f"HTTP状态错误: {e.response.status_code} - {e.response.reason_phrase}"
            )
        except httpx.RequestError as e:
            print(f"请求失败: {e}")
        except KeyError as e:
            print(f"响应数据格式错误: {e}")
        return None
