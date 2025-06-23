from enum import Enum
from typing import Optional, Union


class ResultType(str, Enum):
    TEXT = "text"
    IMAGE_PATH = "image_path"
    IMAGE_BYTES = "image_bytes"
    NONE = "none"


class GalleryResult:
    def __init__(
        self,
        success: bool,
        type_: ResultType,
        content: Optional[Union[str, bytes]] = None,
    ):
        self.success = success
        self.type = type_

        # 只在对应类型里放内容，其他属性都置None
        self.text: Optional[str] = None
        self.image_path: Optional[str] = None
        self.image_bytes: Optional[bytes] = None

        if type_ == ResultType.TEXT and isinstance(content, str):
            self.text = content
        elif type_ == ResultType.IMAGE_PATH and isinstance(content, str):
            self.image_path = content
        elif type_ == ResultType.IMAGE_BYTES and isinstance(content, bytes):
            self.image_bytes = content


# 调用时直接访问对应属性即可，不用判断类型：
# 例如：
# if result.text:
#     print(result.text)
# elif result.image_path:
#     print(result.image_path)
# elif result.image_bytes:
#     # 处理字节数据
#     ...
