import logging
import os
import asyncio
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from interfaces import CharacterInScene, ImageOutput
from langchain_core.messages import HumanMessage, SystemMessage



prompt_template_front = \
"""
根据以下描述生成角色 {identifier} 的全身正面肖像，纯白背景。使用宽幅 16:9 横向画布，而非纵向肖像画布。角色应位于图像中央，占据宽幅画面的中间位置，两侧留有足够的水平空白空间。目光平视前方。站立，双臂自然垂放于身体两侧。表情自然。
特征：{features}
风格：{style}
"""

prompt_template_side = \
"""
根据提供的前视图肖像，生成角色 {identifier} 的全身侧面肖像，纯白背景。使用宽幅 16:9 横向画布，而非纵向肖像画布。角色应位于图像中央，占据宽幅画面的中间位置，两侧留有足够的水平空白空间。面向左侧。站立，双臂自然垂放于身体两侧。
"""

prompt_template_back = \
"""
根据提供的前视图肖像，生成角色 {identifier} 的全身背面肖像，纯白背景。使用宽幅 16:9 横向画布，而非纵向肖像画布。角色应位于图像中央，占据宽幅画面的中间位置，两侧留有足够的水平空白空间。不应看到任何面部特征。
"""


class CharacterPortraitsGenerator:
    def __init__(
        self,
        image_generator,
    ):
        self.image_generator = image_generator


    async def generate_front_portrait(
        self,
        character: CharacterInScene,
        style: str,
    ) -> ImageOutput:
        features = "(静态) " + (character.static_features or "") + "; (动态) " + (character.dynamic_features or "")
        prompt = prompt_template_front.format(
            identifier=character.identifier_in_scene,
            features=features,
            style=style,
        )
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            # size="512x512",
        )
        return image_output

    async def generate_side_portrait(
        self,
        character: CharacterInScene,
        front_image_path: str,
    ) -> ImageOutput:
        prompt = prompt_template_side.format(
            identifier=character.identifier_in_scene,
        )
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=[front_image_path],
            # size="1024x1024",
        )
        return image_output


    async def generate_back_portrait(
        self,
        character: CharacterInScene,
        front_image_path: str,
    ) -> ImageOutput:
        prompt = prompt_template_back.format(
            identifier=character.identifier_in_scene,
        )
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=[front_image_path],
            # size="512x512",
        )
        return image_output