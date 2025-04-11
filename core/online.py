
# import random
# from .utils import download_image

# """
# "龙图示例":"https://git.acwing.com/Est/dragon/-/raw/main/batch1/dragon_222_.jpg"
# """

# """
# "东方": "https://img.paulzzh.tech/",
# "无溅": "https://source.unsplash.com/",
# "缙哥哥": "https://api.dujin.org/pic/yuanshen/",
# "栗次元": "https://t.alcy.cc/"
# """

# urls = {
#     "龙图": "https://git.acwing.com/Est/dragon/-/raw/main/",
#     "搏天": "https://api.btstu.cn/",
#     "樱道": "https://api.r10086.com/",
#     "樱花": "https://www.dmoe.cc/",
#     "保罗": "https://api.paugram.com/",
#     "电狗": "https://api.yimian.xyz/",
#     "诗图": "https://api.likepoems.com/",
#     "萝莉": "https://www.loliapi.com/",
# }

# # online_keys_list = list(urls.keys())

# rule_op = Rule(lambda: conf.is_online)

# dragon = on_command(
#     "龙图", rule=rule_op, aliases={"龙龙", "人机"}, priority=4, block=True
# )


# @dragon.handle()
# async def send_online_image(bot: Bot, event: Event):
#     base_url = "https://git.acwing.com/Est/dragon/-/raw/main/"
#     batch_choice = "batch1/"
#     selected_image_number = random.randint(1, 500)
#     extensions = ".jpg"
#     image_url = f"{base_url}{batch_choice}dragon_{selected_image_number}_{extensions}"

#     if conf.save_online_picture:
#         await picture_main_handle(event, image_url, "人机", "在线", True)
#     else:
#         image_bytes = await download_image(image_url)
#         await bot.send(event, MessageSegment.image(image_bytes))
