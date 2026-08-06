from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict



class Event(BaseModel):
    index: int = Field(
        description="事件的索引，从 0 开始",
    )

    is_last: bool = Field(
        description="指示该事件是否为序列中的最后一个事件"
    )

    description: str = Field(
        description="事件的简明描述，用一句话概括其核心",
        examples=[
            "A thief who stole a gem from a museum was caught after a rooftop chase with guards, and the gem was recovered.",
        ]
    )

    process_chain: List[str] = Field(
        description="构成事件过程链的步骤或动作列表，构成一条完整的因果链。",
        examples=[
            [
                "A thief steals a gem from a museum, triggering the alarm. Guards notice and begin the chase.",
                "The thief rushes out the museum's back door and dashes through narrow alleys, with guards closely pursuing and calling for backup.",
                "The thief climbs a fire escape to the rooftops; the guards follow using low platforms on adjacent buildings.",
                "The thief leaps across a 1.5-meter gap between two buildings. The guards hesitate but take the risky jump, nearly losing their footing.",
                "The thief knocks over stacked wooden planks to create an obstacle. The guards dodge but lose speed.",
                "The thief attempts to slide down a rope to the opposite rooftop, but a guard lunges and grabs their ankle. Both tumble and grapple.",
                "Backup arrives, subduing the thief and recovering the gem.",
            ],
        ]
    )

    def __str__(self):
        s = f"<事件 {self.index}>"
        s += f"\n描述: {self.description}"
        s += f"\n过程链:"
        for process in self.process_chain:
            s += f"\n- {process}"
        return s