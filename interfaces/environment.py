from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict
from PIL import Image



class EnvironmentInScene(BaseModel):
    slugline: str = Field(
        description="场景的场标，指示地点和时间段",
        examples=[
            "INT. COFFEE SHOP - NIGHT",
            "EXT. PARK - DAY",
        ]
    )
    description: str = Field(
        description="特定场景中环境的详细描述。不要在此描述任何角色或动作，仅描述场景设置。",
        examples=[
            "The warm yellow light glowed against the mottled brick wall, while raindrops streaked the glass window with blurred neon reflections. Among the empty booths sat a lone half-finished iced latte—its foam collapsed, a faint lipstick mark on the rim. beads of condensation gleamed on the stainless steel espresso machine, and the record player's turntable rotated slowly in the shadows. A patch of wet floor shimmered with hazy reflected light.",
        ]
    )

    def __str__(self):
        s = f"{self.slugline} -- {self.description}"
        return s


