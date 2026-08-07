import logging
from typing import List, Tuple
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from langchain.chat_models import init_chat_model
from utils.image import image_path_to_b64



system_prompt_template_select_most_consistent_image = \
"""
[角色]
你是一名专业的视觉评估专家。你的专长包括识别候选图片与参考图片之间的角色一致性、空间一致性，以及评估候选图片与文本描述之间的语义一致性。

[任务]
根据用户提供的参考图片、目标图片的文本描述以及若干候选图片，评估哪张候选图片在以下方面表现最佳：
- 角色一致性：候选图片中的角色特征（a. 性别、b. 种族、c. 年龄、d. 面部特征、e. 体型、f. 外观、g. 发型）是否与参考图片中的角色一致。
- 空间一致性：候选图片中角色之间的相对位置（例如角色 A 在左、角色 B 在右、场景布局、视角等空间关系）是否与参考图片一致。
- 描述准确性：候选图片是否准确反映了文本描述的内容（注意：文本描述描述的是我们想要的目标图片，而非编辑指令）。

[输入]
用户将提供以下内容：
- 参考图片：包含角色或其他视角的图片，每张图片附带简短文本描述。例如"参考图片 0：一位身穿红色连衣裙、拥有棕色长发的年轻女孩。"，随后是对应的图片。索引从 0 开始。
- 候选图片：待评估的候选图片。例如"候选图片 0"，随后是一张生成的图片。索引从 0 开始。
- 目标图片文本描述：描述生成的图片应包含什么内容。它被包裹在 <TARGET_DESCRIPTION_START> 和 <TARGET_DESCRIPTION_END> 标签之间。

[输出]
{format_instructions}

[指导原则]
- 优先考虑角色一致性：确保生成图片中的角色在视觉特征（如 a. 性别、b. 种族、c. 年龄、d. 面部特征、e. 体型、f. 外观、g. 发型等）上与参考图片高度一致。
- 关注空间一致性：验证角色的相对位置、物体排列和视角是否与参考图片逻辑一致（例如，如果参考图片中角色 A 在左、角色 B 在右，则生成图片不应颠倒这一关系）。
- 严格对照文本描述：生成图片必须符合文本描述中的关键要素（如动作、场景、物体等），同时忽略与编辑指令相关的部分（因为输入描述反映的是预期结果，而非操作指令）。
- 如果多张图片部分满足条件，选择整体一致性最高的那张；如果没有理想的图片，选择相对最佳选项并说明其不足。
- 确保文本描述中的关键要素都出现在所选图片中。
- 避免主观偏好，所有分析基于客观比较。
- 优先选择没有白边、黑边或任何额外边框的图片。
"""

human_prompt_template_select_most_consistent_image = \
"""
<TARGET_DESCRIPTION_START>
{target_description}
<TARGET_DESCRIPTION_END>
"""


class BestImageResponse(BaseModel):
    best_image_index: int = Field(
        ...,
        description="最佳图片的索引。"
    )
    reason: str = Field(
        ...,
        description="该图片被评为最佳的原因。"
    )


class BestImageSelector:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        chat_model: str,
    ):

        self.chat_model = init_chat_model(
            model=chat_model,
            model_provider="openai",
            base_url=base_url,
            api_key=api_key,
        )


    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"因 {retry_state.outcome.exception()} 正在重试最佳图片选择"),
    )
    async def __call__(
        self,
        reference_image_path_and_text_pairs: List[Tuple[str, str]],
        target_description: str,
        candidate_image_paths: List[str],
    ) -> str:
        """
        Args:
            ref_image_path_and_text_pairs:
            包含参考图片路径及其描述的元组列表。

            target_description:
            目标图片的描述文本。

            candidate_image_paths:
            待评估的候选图片路径列表。
        """

        if not candidate_image_paths:
            logging.warning("未提供候选图片；跳过最佳图片选择")
            raise ValueError("没有候选图片可供选择")

        logging.info(f"正在从候选图片中选择最佳图片: {candidate_image_paths}")

        human_content = []
        for idx, (ref_image_path, text) in enumerate(reference_image_path_and_text_pairs):
            human_content.append({
                "type": "text",
                "text": f"参考图片 {idx}: {text}"
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(ref_image_path, mime=True)}
            })

        for idx, candidate_image_path in enumerate(candidate_image_paths):
            human_content.append({
                "type": "text",
                "text": f"候选图片 {idx}"
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(candidate_image_path, mime=True)}
            })
        human_content.append({
            "type": "text",
            "text": human_prompt_template_select_most_consistent_image.format(target_description=target_description)
        })

        parser = PydanticOutputParser(pydantic_object=BestImageResponse)

        messages = [
            SystemMessage(content=system_prompt_template_select_most_consistent_image.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_content)
        ]

        chain = self.chat_model | parser

        response = await chain.ainvoke(messages)
        idx = response.best_image_index
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidate_image_paths):
            logging.warning(f"收到无效的 best_image_index={idx}；默认为 0")
            idx = 0
        best_image_path = candidate_image_paths[idx]
        logging.info(f"已选择最佳图片: {best_image_path}")
        logging.info(f"选择原因: {response.reason}")
        return best_image_path