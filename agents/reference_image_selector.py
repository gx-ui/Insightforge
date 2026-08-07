import logging
from typing import List, Tuple
from tenacity import retry, stop_after_attempt
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from langchain.chat_models import init_chat_model
from utils.image import image_path_to_b64

from utils.retry import after_func

system_prompt_template_select_reference_images_only_text = \
"""
[角色]
你是一名专业的视觉创作助手，擅长多模态图像分析和推理。

[任务]
你的核心任务是根据用户的文本描述（描述目标帧），从提供的参考图片描述集合（包括多张角色参考图片和先前帧的现有场景图片）中智能选择最合适的参考图片，确保后续生成的图片满足以下关键一致性：
- 角色一致性：生成角色的外观（如性别、种族、年龄、面部特征、发型、体型）、服装、表情、姿势等应与参考图片描述高度匹配。
- 环境一致性：生成图片的场景（如背景、光线、氛围、布局）应与先前帧的现有图片描述保持一致。
- 风格一致性：生成图片的视觉风格（如写实、卡通、电影感、色调）应与参考图片描述协调。

[输入]
你将收到目标帧的文本描述，以及一系列参考图片描述。
- 目标帧的文本描述被包裹在 <FRAME_DESC> 和 </FRAME_DESC> 之间。
- 参考图片描述序列被包裹在 <SEQ_DESC> 和 </SEQ_DESC> 之间。每个描述都以其索引为前缀，从 0 开始。

以下是输入格式示例：
<FRAME_DESC>
[Camera 1] 从 Alice 的过肩视角拍摄。Alice 在靠近摄影机的一侧，只有她的肩膀出现在画面左下角。Bob 在远离摄影机的一侧，位于画面中央偏右。Bob 的表情从惊讶转为欣喜，因为他认出了 Alice。
</FRAME_DESC>

<SEQ_DESC>
Image 0: Alice 的正面肖像。
Image 1: Bob 的正面肖像。
Image 2: [Camera 0] 超市过道的中景。Alice 和 Bob 以侧面轮廓面向画面右侧。Bob 在画面右侧，Alice 在左侧。Alice 低头推着购物车，紧跟 Bob 身后，不小心撞到了他的脚后跟。
Image 3: [Camera 1] 从 Alice 的过肩视角拍摄。Alice 在靠近摄影机的一侧，只有她的肩膀出现在画面左下角。Bob 在远离摄影机的一侧，位于画面中央偏右。Bob 迅速转身，表情从中性转为惊讶。
Image 4: [Camera 2] 从 Bob 的过肩视角拍摄。Bob 在靠近摄影机的一侧，只有他的肩膀出现在画面右下角。Alice 在远离摄影机的一侧，位于画面中央偏左。Alice 低头，然后抬头准备道歉。在意识到是熟人后，她的表情转为惊讶。
</SEQ_DESC>


[输出]
你需要根据用户的描述选择最多 8 张最相关的参考图片，并将相应的索引放入输出的 ref_image_indices 字段中。同时，你应该生成一个文本提示，描述要创建的图片，指定生成图片中的哪些元素应参考哪张图片描述（以及其中的哪些元素）。

{format_instructions}


[指导原则]
- 确保所有输出值（不含键）的语言与帧描述使用的语言一致。
- 参考图片描述可能从不同角度、不同着装或不同场景中描绘同一角色。识别最接近用户所描述版本的那个描述。
- 优先选择构图相似的图片描述，即由同一摄影机拍摄的镜头。
- 先前帧的图片按时间顺序排列。给予较新的图片（更接近序列末尾的）更高的优先级。
- 选择尽可能简洁的参考图片描述，避免包含重复信息。例如，如果 Image 3 从正面描绘了 Bob 的面部特征，而 Image 1 也从正面肖像描绘了 Bob 的面部特征，那么 Image 1 是冗余的，不应被选中。
- 当帧描述中出现新角色时，优先选择其肖像图片描述（如果有的话），以确保准确描绘其外观。注意角色是正面、侧面还是背面朝向摄影机。选择最合适的视角作为角色的参考图片。
- 对于角色肖像，你只能从多个视角（正面、侧面、背面）中最多选择一张图片。根据帧描述选择最合适的一张。例如，当从侧面描绘角色时，选择角色的侧面视角。
- 最多选择 **8** 个最优参考图片描述。
"""


system_prompt_template_select_reference_images_multimodal = \
"""
[角色]
你是一名专业的视觉创作助手，擅长多模态图像分析和推理。

[任务]
你的核心任务是根据用户的文本描述（描述目标帧），从提供的参考图片库（包括多张角色参考图片和先前帧的现有场景图片）中智能选择最合适的参考图片，确保后续生成的图片满足以下关键一致性：
- 角色一致性：生成角色的外观（如性别、种族、年龄、面部特征、发型、体型）、服装、表情、姿势等应与参考图片高度匹配。
- 环境一致性：生成图片的场景（如背景、光线、氛围、布局）应与先前帧的现有图片保持一致。
- 风格一致性：生成图片的视觉风格（如写实、卡通、电影感、色调）应与参考图片和现有图片协调。

[输入]
你将收到目标帧的文本描述，以及一系列参考图片。
- 目标帧的文本描述被包裹在 <FRAME_DESC> 和 </FRAME_DESC> 之间。
- 参考图片序列被包裹在 <SEQ_IMAGES> 和 </SEQ_IMAGES> 之间。每张参考图片都附带文本描述。参考图片索引从 0 开始。

以下是输入格式示例：
<FRAME_DESC>
[Camera 1] 从 Alice 的过肩视角拍摄。<Alice> 在靠近摄影机的一侧，只有她的肩膀出现在画面左下角。<Bob> 在远离摄影机的一侧，位于画面中央偏右。<Bob> 的表情从惊讶转为欣喜，因为他认出了 <Alice>。
</FRAME_DESC>

<SEQ_IMAGES>
Image 0: Alice 的正面肖像。
[Image 0 here]
Image 1: Bob 的正面肖像。
[Image 1 here]
Image 2: [Camera 0] 超市过道的中景。Alice 和 Bob 以侧面轮廓面向画面右侧。Bob 在画面右侧，Alice 在左侧。Alice 低头推着购物车，紧跟 Bob 身后，不小心撞到了他的脚后跟。
[Image 2 here]
Image 3: [Camera 1] 从 Alice 的过肩视角拍摄。Alice 在靠近摄影机的一侧，只有她的肩膀出现在画面左下角。Bob 在远离摄影机的一侧，位于画面中央偏右。Bob 背对摄影机。
[Image 3 here]
Image 4: [Camera 2] 从 Bob 的过肩视角拍摄。Bob 在靠近摄影机的一侧，只有他的肩膀出现在画面右下角。Alice 在远离摄影机的一侧，位于画面中央偏左。Alice 低头，然后抬头准备道歉。在意识到是熟人后，她的表情转为惊讶。
</SEQ_IMAGES>

[输出]
你需要根据用户的描述选择最相关的参考图片，并将相应的索引放入输出的 `ref_image_indices` 字段中。同时，你应该生成一个文本提示，描述要创建的图片，指定生成图片中的哪些元素应参考哪张图片（以及其中的哪些元素）。

{format_instructions}


[指导原则]
- 确保所有输出值（不含键）的语言与帧描述使用的语言一致。
- 参考图片描述可能从不同角度、不同着装或不同场景中描绘同一角色。识别最接近用户所描述版本的那个描述。
- 优先选择构图相似的图片描述，即由同一摄影机拍摄的镜头。
- 先前帧的图片按时间顺序排列。给予较新的图片（更接近序列末尾的）更高的优先级。
- 选择尽可能简洁的参考图片描述，避免包含重复信息。例如，如果 Image 3 从正面描绘了 Bob 的面部特征，而 Image 1 也从正面肖像描绘了 Bob 的面部特征，那么 Image 1 是冗余的，不应被选中。
- 对于角色肖像，你只能从多个视角（正面、侧面、背面）中最多选择一张图片。根据帧描述选择最合适的一张。例如，当从侧面描绘角色时，选择角色的侧面视角。
- 最多选择 **8** 个最优参考图片描述。
- 指导图片编辑的文本应尽可能简洁。
"""


human_prompt_template_select_reference_images = \
"""
<FRAME_DESC>
{frame_description}
</FRAME_DESC>
"""




class RefImageIndicesAndTextPrompt(BaseModel):
    ref_image_indices: List[int] = Field(
        description="从提供的图片中选择的参考图片索引。例如，[0, 2, 5] 表示选择第一张、第三张和第六张图片。索引从 0 开始。",
        examples=[
            [1, 3]
        ]
    )
    text_prompt: str = Field(
        description="指导图片生成的文本描述。你需要描述要生成的图片，指定生成图片中的哪些元素应参考哪张图片（以及其中的哪些元素）。例如，'根据以下描述创建图片：\n男士站在风景中。男士应参考 Image 0。风景应参考 Image 1。' 这里，参考图片的索引应指向其在 ref_image_indices 列表中的位置，而非在提供的图片列表中的序号。引用参考图片必须使用 Image N 的格式。除了 Image 之外，不要使用任何其他词语。",
        examples=[
            "根据以下指导创建图片：\n 基于 Image 1 进行修改：Bob 的身体转向摄影机，而所有其他元素保持不变。Bob 的外观应参考 Image 0。",
            "根据以下描述创建图片：\n男士站在风景中。男士应参考 Image 0。风景应参考 Image 1。"
        ]
    )



class ReferenceImageSelector:
    def __init__(
        self,
        chat_model,
    ):

        self.chat_model = chat_model


    @retry(
        stop=stop_after_attempt(3),
        after=after_func,
    )
    async def select_reference_images_and_generate_prompt(
        self,
        available_image_path_and_text_pairs: List[Tuple[str, str]],
        frame_description: str,
    ):
        filtered_image_path_and_text_pairs = available_image_path_and_text_pairs

        # 1. 使用纯文本模型筛选图片
        if len(available_image_path_and_text_pairs) >= 8:
            human_content = []
            for idx, (_, text) in enumerate(available_image_path_and_text_pairs):
                human_content.append({
                    "type": "text",
                    "text": f"Image {idx}: {text}"
                })
            human_content.append({
                "type": "text",
                "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
            })
            parser = PydanticOutputParser(pydantic_object=RefImageIndicesAndTextPrompt)

            messages = [
                SystemMessage(content=system_prompt_template_select_reference_images_only_text.format(format_instructions=parser.get_format_instructions())),
                HumanMessage(content=human_content)
            ]

            chain = self.chat_model | parser

            try:
                ref = await chain.ainvoke(messages)
                filtered_image_path_and_text_pairs = select_pairs_by_indices(available_image_path_and_text_pairs, ref.ref_image_indices)
                logging.info(f"已筛选图片 idx:{ref.ref_image_indices}")

            except Exception as e:
                logging.error(f"获取图片 prompt 出错: \n{e}")
                raise e

        # 2. 使用多模态模型筛选图片
        human_content = []
        for idx, (image_path, text) in enumerate(filtered_image_path_and_text_pairs):
            human_content.append({
                "type": "text",
                "text": f"Image {idx}: {text}"
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(image_path)}
            })
        human_content.append({
            "type": "text",
            "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
        })

        parser = PydanticOutputParser(pydantic_object=RefImageIndicesAndTextPrompt)

        messages = [
            SystemMessage(content=system_prompt_template_select_reference_images_multimodal.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_content)
        ]

        chain = self.chat_model | parser

        try:
            response = await chain.ainvoke(messages)
            reference_image_path_and_text_pairs = select_pairs_by_indices(filtered_image_path_and_text_pairs, response.ref_image_indices)
            return {
                "reference_image_path_and_text_pairs": reference_image_path_and_text_pairs,
                "text_prompt": response.text_prompt,
            }

        except Exception as e:
            logging.error(f"获取图片 prompt 出错: \n{e}")
            raise e




def select_pairs_by_indices(pairs, indices):
    """使用 LLM 发射的索引访问配对，拒绝越界值。"""

    invalid = [i for i in indices if i < 0 or i >= len(pairs)]
    if invalid:
        raise ValueError(f"ref_image_indices 超出范围: {invalid}（共有 {len(pairs)} 张图片）")
    return [pairs[i] for i in indices]