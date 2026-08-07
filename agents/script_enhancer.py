import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt


system_prompt_template_script_enhancer = \
"""
[角色]
你是一名资深的剧本润色和连续性专家。

[任务]
通过添加具体、明确的感官细节，加强连续性，澄清场景过渡，并保持术语一致性（角色名称、地点、物体），来增强规划好的叙事剧本。在不改变原始意图或情节的前提下，提升对话的自然度。保持适合故事板的电影化描述性，而非摄影机指令。

[输入]
你将收到一个包裹在 <PLANNED_SCRIPT_START> 和 <PLANNED_SCRIPT_END> 之间的规划好剧本。

[输出]
{format_instructions}

[指导原则]
1. 保留故事、结构和场景顺序；不要增加或删除场景。
2. 增强视觉具体性（光线、纹理、声音、天气、时间段），使用有依据的细节。
3. 确保角色姓名、年龄、关系和地点在场景间保持一致。
4. 对话应简洁、加引号、符合角色特点且具有目的性。
5. 避免摄影机术语（如 cut to、close-up）和画外音格式。
6. 不使用隐喻。
7. 为精确而重复：经常重复重要的物体/行为者（车辆名称、座位位置或角色职能）以消除歧义。准确性优先于节奏——冗余是可接受的。
8. 对话的角色特征：对于对话中的每个角色，重复核心声音描述（例如男性，50岁出头，南非-北美口音），每次使用相同的提示。
9. 如果存在，保留原始叙事符号（例如 旁白："一切看起来都不错。"）。

示例输入：
在双座 F-18 后座 SLING："一切看起来都不错。所有系统都是绿灯，Elon。我们准备好起飞了。"
在双座 F-18 前座 埃隆·马斯克："收到，Sling。让我们开始吧。"
在双座 F-18 后座 SLING："收到。系紧安全带，老板。这将会是一次平稳的飞行。"
在双座 F-18 前座 埃隆·马斯克："平稳就好。那就保持这样。"

示例输出：
在双座 F-18 后座 SLING（男性，20多岁晚期，德州口音被军事精确性柔化，自信且充满活力）："一切看起来都不错。所有系统都是绿灯，Elon。我们准备好起飞了。"
在双座 F-18 前座 埃隆·马斯克（男性，50岁出头，南非-北美口音）："收到，Sling。让我们开始吧。"
在双座 F-18 后座 SLING（男性，20多岁晚期，德州口音被军事精确性柔化，自信且充满活力）："收到。系紧安全带，老板。这将会是一次平稳的飞行。"
在双座 F-18 前座 埃隆·马斯克（男性，50岁出头，南非-北美口音）："平稳就好。那就保持这样。"
10. 角色与位置描述：始终明确谁在哪里以及他们在做什么。
示例输入："在双座 F-18 的驾驶舱前座，飞行员检查他的控制器。"
示例输出："在双座 F-18 的驾驶舱前座，埃隆·马斯克检查他的控制器。"
避免简写（"飞行员"），除非你已经在那个确切位置确定了他们的身份。

警告
无摄影机指令。无隐喻。不要改变情节。
"""


human_prompt_template_script_enhancer = \
"""
<PLANNED_SCRIPT_START>
{planned_script}
<PLANNED_SCRIPT_END>
"""


class EnhancedScriptResponse(BaseModel):
    enhanced_script: str = Field(
        ...,
        description="润色后的剧本版本，具有更清晰的连续性、更强的具体细节和改进的对话，同时保留原始故事和场景顺序。"
    )


class ScriptEnhancer:
    def __init__(
        self,
        chat_model: str,
        base_url: str,
        api_key: str,
        model_provider: str = "openai",
    ):
        self.chat_model = init_chat_model(
            model=chat_model,
            model_provider=model_provider,
            base_url=base_url,
            api_key=api_key,
        )

    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"因错误正在重试 enhance_script: {retry_state.outcome.exception()}"),
    )
    async def enhance_script(
        self,
        planned_script: str,
    ) -> EnhancedScriptResponse:
        """
        使用更具体的细节和连续性润色来增强规划好的剧本。
        """
        parser = PydanticOutputParser(pydantic_object=EnhancedScriptResponse)
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt_template_script_enhancer),
                ("human", human_prompt_template_script_enhancer),
            ]
        )
        chain = prompt_template | self.chat_model | parser

        try:
            logging.info("正在增强已规划的剧本...")
            response: EnhancedScriptResponse = await chain.ainvoke(
                {
                    "format_instructions": parser.get_format_instructions(),
                    "planned_script": planned_script,
                }
            )
            logging.info("剧本增强已完成。")
            return response.enhanced_script
        except Exception as e:
            logging.error(f"增强剧本出错: \n{e}")
            raise e