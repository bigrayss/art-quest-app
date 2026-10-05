# -*- coding: utf-8 -*-
"""English text for the mission library — derived from the rows in `missions.py`.

`missions.py` is the measurement instrument: its Chinese titles and instructions
must stay byte-for-byte what was shown to the children already recorded, so this
module never touches it. Instead it reads the ASCII metadata every generated row
already carries (`family`, `form_id`, `condition`, `task_id`) and rebuilds the
same sentence in English, phrase for phrase. A translation, not a rewrite: the
demands and limits of each task are what is being measured, so they are kept
identical; only the wording is in plain, short English for a 6–14-year-old.

    translate_task(task)   -> shallow copy with title / instruction / prompt /
                              hint / family_name / type / phases[*].label in
                              English, plus "lang": "en"
    translate_family(fam)  -> copy of a `/families` row with `name` in English
    FAMILY_NAMES_EN        -> {"M0": "Free Drawing", ...}
"""
from typing import Any, Dict, List, Optional

FAMILY_NAMES_EN: Dict[str, str] = {
    "M0": "Free Drawing",
    "M1": "Museum Restorer",
    "M2": "Explorer's Sketch",
    "M3": "Lost Pieces",
    "M4": "Mutant Object Lab",
    "M5": "Fusion Inventor",
    "M6": "Mood World",
    "M7": "Line Adventure",
    "M8": "Impossible World",
    "M9": "Story Challenge",
}

PHASE_LABELS_EN: Dict[str, str] = {
    "lines": "Lines only",
    "develop": "Make it a picture",
}

# -- M0: the five original open-creation tasks, keyed by task_id -------------
M0_EN: Dict[str, Dict[str, str]] = {
    "emotion_alone": {
        "title": "Draw “lonely” or “happy”",
        "instruction": "Do not just draw a face or an expression. Use colour, space, objects and layout "
                       "so the whole picture itself gives one feeling: “lonely” or “happy”.",
        "hint": "Think: is this feeling big or small? Empty or crowded? Cold or warm?",
    },
    "imagine_animal": {
        "title": "Design an animal that does not exist",
        "instruction": "Create an animal the world has never seen. Where does it live? What does it eat? "
                       "What special thing can it do? Draw it and the place it lives.",
        "hint": "You can mix the features of two or three animals or objects you know, then change the size and proportions.",
    },
    "transform_chair": {
        "title": "A chair turned into…",
        "instruction": "Start from an ordinary chair and turn it into something with a completely different use: "
                       "a vehicle, a creature, a building, an instrument, anything. People should still be able "
                       "to tell it used to be a chair.",
        "hint": "First decide which parts to keep and which to change, then decide its new job.",
    },
    "color_rain_city": {
        "title": "A rainy city in only three colours",
        "instruction": "Pick three colours (black and white do not count) and draw a rainy city using only those three. "
                       "Find ways to show near and far, light and dark, and the feeling of rain.",
        "hint": "The same colour can be darker or lighter, and colours can be layered.",
    },
    "story_character_home": {
        "title": "My character and its home",
        "instruction": "Create a character of your own and draw its home. The home should show what this character "
                       "likes, what it is afraid of, and what it does every day.",
        "hint": "The character can be tiny and the home huge, or the other way round. Let the objects tell the character's story.",
    },
}

# -- M1 / M2 / M3 / M5 / M6 / M7 / M9 prompt banks, keyed by form letter ------
M1_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "Museum rescue",
          "instruction": "A painting in the museum is damaged. Use the reference picture to redraw the important "
                         "objects, where they are and how they fit together, so people can still recognise the scene."},
    "B": {"title": "The explorer's lost photo",
          "instruction": "One of the expedition's photos is ruined. Redraw this place so the next explorer knows "
                         "what is here and where each thing is."},
    "C": {"title": "The detective's scene",
          "instruction": "The detective only found a damaged picture of the scene. Redraw the important structures "
                         "so other detectives can understand this place."},
    "D": {"title": "Fixing the robot's memory",
          "instruction": "A robot has only this visual record of the place left. Help it rebuild the scene."},
}
M1_HINT_EN = "Set the big shapes and positions first, then add details."

M2_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "Alien field notes",
          "instruction": "You have just landed on an unknown planet. Draw a record so the next explorer knows what "
                         "these things look like, which is in front and which is behind."},
    "B": {"title": "The scientist's sketchbook",
          "instruction": "You are a scientist. Record the size, shape and position of these objects accurately."},
    "C": {"title": "Treasure-hunt site",
          "instruction": "This is an important spot on the treasure map. Record where the objects are and which ones "
                         "cover others, so another person could set the scene up again."},
    "D": {"title": "Teaching a robot to see",
          "instruction": "A robot does not understand space. Draw this scene so it knows which object is bigger, "
                         "which is closer, and which is hidden behind another."},
}
M2_HINT_EN = "Notice who is in front, who is hidden, and who is bigger."

M3_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "The lost painting",
          "instruction": "We only found a few pieces of the original painting. Turn them into a whole picture and "
                         "tell us what happened here."},
    "B": {"title": "Mystery message",
          "instruction": "Someone left some strange marks. Maybe they belong to a bigger world. Grow them into a "
                         "complete picture."},
    "C": {"title": "Pieces of a dream",
          "instruction": "These shapes are pieces left behind by a dream. Turn them into the whole dream."},
    "D": {"title": "The broken portal",
          "instruction": "A portal broke down and left only these pieces behind. Draw what the place on the other side was."},
}
M3_HINT_EN = "You can turn the pieces around in your head, and you can use only some of them."
# same order as missions.M3_NARRATIVE; form i uses card i % len
M3_NARRATIVE_EN: List[str] = [
    "Something has just arrived.",
    "Something is hiding.",
    "There is a celebration here.",
    "Something is about to change.",
    "There is something here that does not belong.",
]

M5_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "Mixed creature",
          "instruction": "Fuse two completely different things into one new creature. Do not just put them side by "
                         "side: make them truly become one whole."},
    "B": {"title": "Future invention",
          "instruction": "Fuse these two things into an invention from the future."},
    "C": {"title": "Impossible building",
          "instruction": "If these two things became one building together, what would it look like?"},
    "D": {"title": "Double identity",
          "instruction": "Design a new thing. At first glance people see A; when they look closely they find it is also B."},
}
M5_HINT_EN = "Do not just put the two together. Let them grow into one thing."
M5_NOUNS_EN: Dict[str, str] = {
    "castle": "a castle", "jellyfish": "a jellyfish", "cat": "a cat", "airplane": "an airplane",
    "train": "a train", "tree": "a tree", "robot": "a robot", "flower": "a flower",
    "shoe": "a shoe", "house": "a house", "whale": "a whale", "school": "a school",
    "backpack": "a backpack", "bird": "a bird", "clock": "a clock", "octopus": "an octopus",
}
M5_TITLE_NOUNS_EN: Dict[str, str] = {
    "castle": "Castle", "jellyfish": "Jellyfish", "cat": "Cat", "airplane": "Airplane",
    "train": "Train", "tree": "Tree", "robot": "Robot", "flower": "Flower",
    "shoe": "Shoe", "house": "House", "whale": "Whale", "school": "School",
    "backpack": "Backpack", "bird": "Bird", "clock": "Clock", "octopus": "Octopus",
}

M6_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "Mood switch", "instruction": "Make this ordinary scene feel {mood}."},
    "B": {"title": "Weather wizard", "instruction": "Make this place look like a big storm is about to arrive."},
    "C": {"title": "Two worlds",
          "instruction": "In one picture, one side is safe and the other side is dangerous. Use colour and visual "
                         "changes so people can see the difference at a glance."},
    "D": {"title": "The hidden hero",
          "instruction": "Use colour so the viewer notices the most important thing first, but do not make everything "
                         "else completely dark."},
    "E": {"title": "Time machine", "instruction": "Show this same place {when}."},
}
M6_HINT_EN = "The same colour can be painted darker or lighter."
M6_MOOD_EN: Dict[str, str] = {"calm": "calm", "mysterious": "mysterious", "exciting": "exciting", "dangerous": "dangerous"}
M6_WHEN_EN: Dict[str, str] = {"midnight": "at midnight", "sunrise": "at sunrise", "other_planet": "on another planet",
                              "after_100_years": "one hundred years from now"}

M7_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "Magic lines", "instruction": "these lines suddenly have magic. What have they turned into?"},
    "B": {"title": "Drawing a sound",
          "instruction": "if a sound could be seen, what would it look like? Then grow it into a complete picture."},
    "C": {"title": "Line monsters",
          "instruction": "the lines you just drew have come alive. What kind of world have they become?"},
}
M7_HINT_EN = "Thick or thin, fast or slow, close together or far apart: the lines can all say something."
M7_CONCEPTS_EN: Dict[str, str] = {
    "wind": "wind", "whisper": "a whisper", "explosion": "an explosion", "rain": "rain", "speed": "speed",
    "heavy": "heavy", "nervous": "nervous", "calm": "calm", "bouncing": "bouncing", "growing": "growing",
}

M8_TITLE_EN = "Impossible World"
M8_INSTRUCTION_EN = ("Design a world where all the rules below are true. Draw how the people or creatures "
                     "here live, and what is happening.")
M8_HINT_EN = "First decide how these rules would change life here, then start drawing."
# same category and index scheme as missions.M8_RULES ("physics:0" etc.)
M8_RULES_EN: Dict[str, List[str]] = {
    "physics": ["Gravity goes sideways.", "Water floats in the sky.", "Shadows walk around on their own.",
                "At night everything becomes light."],
    "scale": ["Plants are bigger than buildings.", "People are smaller than insects.",
              "A mountain fits inside one room."],
    "life": ["Houses are alive.", "Animals build the cities.", "People grow wings when they need them.",
             "Machines and plants live together."],
    "environment": ["The whole city is under water.", "Everyone lives above the clouds.",
                    "The world is inside one giant tree.", "The ground is made of moving islands."],
}

M9_EN: Dict[str, Dict[str, str]] = {
    "A": {"title": "A door you have never seen",
          "instruction": "You open a door you have never seen before. What is behind it?"},
    "B": {"title": "Everything got small",
          "instruction": "One day everything in the city suddenly got small, except one thing that stayed its normal size."},
    "C": {"title": "The talking thing",
          "instruction": "An ordinary object suddenly learns to talk. What does it want to do most?"},
    "D": {"title": "Something in the sky",
          "instruction": "Something nobody has ever seen suddenly appears in the sky. What is happening?"},
    "E": {"title": "A place that does not exist",
          "instruction": "You find a map with a place on it that does not exist. Draw the place you finally find."},
}
M9_HINT_EN = "Let the things in the picture tell the story for you."

# -- M4: base object × environment × goal, three prompt styles ----------------
M4_BASE_EN: Dict[str, str] = {"umbrella": "umbrella", "shoe": "shoe", "backpack": "backpack", "chair": "chair",
                              "teapot": "teapot", "clock": "clock", "lamp": "lamp", "bicycle": "bicycle"}
# each environment carries its own preposition: "under the sea" / "in the desert"
M4_ENV_EN: Dict[str, str] = {"underwater": "under the sea", "outer space": "in outer space", "desert": "in the desert",
                             "frozen world": "in a frozen world", "giant forest": "in a giant forest",
                             "floating city": "in a floating city"}
M4_GOAL_EN: Dict[str, str] = {"transportation": "vehicle", "shelter": "shelter", "creature": "creature",
                              "rescue machine": "rescue machine", "home": "home", "exploration tool": "exploring tool"}
M4_TEMPLATES_EN: Dict[str, str] = {
    "minimal": "Turn the {base} into {a_goal} that works {env}.",
    "story": "You are stuck {env} and all you have is {a_base}. Turn it into {a_goal} that can help you.",
    "challenge": "Turn the {base} into {a_goal} {env}. But it must still look like {a_base}, "
                 "and it must serve at least two creatures.",
}
M4_HINT_EN = "Think about which part of it to keep and which part to change."


def _form_letter(task: Dict[str, Any]) -> str:
    """The prompt-bank letter for a generated form: "A", "A_calm", "WIND_A" -> A."""
    form = str(task.get("form_id") or "")
    fam = task.get("family")
    if fam in ("M5", "M7"):
        return form.rsplit("_", 1)[-1]
    return form.split("_", 1)[0]


def _m0(task: Dict[str, Any]) -> Dict[str, str]:
    return dict(M0_EN[task["task_id"]])


def _m1(task: Dict[str, Any]) -> Dict[str, str]:
    return {**M1_EN[_form_letter(task)], "hint": M1_HINT_EN}


def _m2(task: Dict[str, Any]) -> Dict[str, str]:
    return {**M2_EN[_form_letter(task)], "hint": M2_HINT_EN}


def _m3(task: Dict[str, Any]) -> Dict[str, str]:
    letter = _form_letter(task)
    i = "ABCD".index(letter)
    card = M3_NARRATIVE_EN[i % len(M3_NARRATIVE_EN)]
    bank = M3_EN[letter]
    return {"title": bank["title"],
            "instruction": f"{bank['instruction']}\n\nAlso, in this picture: {card}",
            "hint": M3_HINT_EN}


def _an(noun: str) -> str:
    """'a shoe' / 'an umbrella' — the article the noun wants."""
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


def _m4(task: Dict[str, Any]) -> Dict[str, str]:
    cond = task.get("condition") or {}
    style = task.get("prompt_style") or str(task.get("form_id", "")).rsplit("_", 1)[-1]
    base, env, goal = M4_BASE_EN[cond["base_object"]], M4_ENV_EN[cond["environment"]], M4_GOAL_EN[cond["goal"]]
    text = M4_TEMPLATES_EN[style].format(base=base, a_base=_an(base), env=env, a_goal=_an(goal))
    return {"title": f"{base.capitalize()} \u2192 {goal}", "instruction": text, "hint": M4_HINT_EN}


def _m5(task: Dict[str, Any]) -> Dict[str, str]:
    cond = task.get("condition") or {}
    a, b = cond["concept_a"], cond["concept_b"]
    bank = M5_EN[_form_letter(task)]
    return {"title": f"{M5_TITLE_NOUNS_EN[a]} + {M5_TITLE_NOUNS_EN[b]}",
            "instruction": f"{bank['instruction']}\n\nThis time, fuse: {M5_NOUNS_EN[a]} and {M5_NOUNS_EN[b]}.",
            "hint": M5_HINT_EN}


def _m6(task: Dict[str, Any]) -> Dict[str, str]:
    cond = task.get("condition") or {}
    letter = _form_letter(task)
    bank = M6_EN[letter]
    text = bank["instruction"]
    if "mood" in cond:
        text = text.format(mood=M6_MOOD_EN[cond["mood"]])
    elif "when" in cond:
        text = text.format(when=M6_WHEN_EN[cond["when"]])
    return {"title": bank["title"], "instruction": text, "hint": M6_HINT_EN}


def _m7(task: Dict[str, Any]) -> Dict[str, str]:
    cond = task.get("condition") or {}
    bank = M7_EN[_form_letter(task)]
    phases = task.get("phases") or []
    seconds = phases[0]["seconds"] if phases else 60
    concept = M7_CONCEPTS_EN[cond["concept"]]
    text = (f"Step 1 ({seconds} seconds): do not draw any real thing. Use only lines to show “{concept}”.\n\n"
            f"Step 2: do not erase the lines you just drew. Now, {bank['instruction']}")
    return {"title": bank["title"], "instruction": text, "hint": M7_HINT_EN}


def _m8(task: Dict[str, Any]) -> Dict[str, str]:
    cond = task.get("condition") or {}
    rules = []
    for ref in cond.get("rule_refs") or []:
        cat, idx = ref.split(":")
        rules.append(M8_RULES_EN[cat][int(idx)])
    text = M8_INSTRUCTION_EN + "\n\n" + "\n".join(f"· {r}" for r in rules)
    return {"title": M8_TITLE_EN, "instruction": text, "hint": M8_HINT_EN}


def _m9(task: Dict[str, Any]) -> Dict[str, str]:
    return {**M9_EN[_form_letter(task)], "hint": M9_HINT_EN}


_BY_FAMILY = {"M0": _m0, "M1": _m1, "M2": _m2, "M3": _m3, "M4": _m4, "M5": _m5,
              "M6": _m6, "M7": _m7, "M8": _m8, "M9": _m9}


def translate_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """English copy of one library row. The input is never modified.

    Rows this module cannot rebuild (a researcher-supplied task from `tasks.json`
    with an unknown family or form) come back unchanged except for `lang`, so a
    custom task still shows — in whatever language it was written.
    """
    out = dict(task)
    fam = task.get("family")
    builder = _BY_FAMILY.get(fam)
    en: Optional[Dict[str, str]] = _v2(task)      # v2.2 的题按 task_id 直接给
    if en is None and builder is not None:
        try:
            en = builder(task)
        except (KeyError, ValueError, IndexError):
            en = None
    if en is not None:
        out["title"] = en["title"]
        out["instruction"] = en["instruction"]
        out["prompt"] = en["instruction"]
        out["hint"] = en["hint"]
    if fam in FAMILY_NAMES_EN:
        out["family_name"] = FAMILY_NAMES_EN[fam]
        out["type"] = FAMILY_NAMES_EN[fam]
    if task.get("phases"):
        out["phases"] = [{**p, "label": PHASE_LABELS_EN.get(p.get("id", ""), p.get("label", ""))}
                         for p in task["phases"]]
    out["lang"] = "en"
    return out


def translate_family(fam: Dict[str, Any]) -> Dict[str, Any]:
    """A `/families` row with its name in English; everything else untouched."""
    out = dict(fam)
    name = FAMILY_NAMES_EN.get(fam.get("id", ""))
    if name:
        out["name"] = name
    return out


def translate_library(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [translate_task(t) for t in tasks]


# ---------------------------------------------------------------------------
# v2.2（2026-10-01）：按 task_id 直接给英文。中文题面在 missions_v2.py。
# M7 只给第一步的概念句和第二步；M8 只给说明和规则，开头固定。
# ---------------------------------------------------------------------------
V2_EN: Dict[str, Dict[str, Any]] = {
    # M0
    "M0_A1": {"title": "Superpower", "instruction": "Draw what happens the first time you use a superpower.", "hint": "Strange can still be useful."},
    "M0_A2": {"title": "A car without wheels", "instruction": "Draw a vehicle without wheels. Think about how it moves.", "hint": "First decide how it moves, then what it looks like."},
    "M0_E3": {"title": "Monster restaurant", "instruction": "Draw a restaurant only for monsters. Show what they are eating.", "hint": "What is on the menu?"},
    "M0_E4": {"title": "How food feels", "instruction": "Choose a food. Draw its personality and how it feels today.", "hint": "It can have arms and legs."},
    "M0_E5": {"title": "The last game level", "instruction": "Draw the last level of a game.", "hint": "The boss does not have to be a monster."},
    "M0_J3": {"title": "Underwater city", "instruction": "Draw an underwater city. Show how people live there.", "hint": "Where does the light come from?"},
    "M0_J4": {"title": "Robot and plants", "instruction": "Draw a place where a robot and plants live together. Think about who looks after whom.", "hint": "A machine can grow plants too."},
    "M0_J5": {"title": "The gym at night", "instruction": "At night, the gym becomes another world. Draw what it looks like.", "hint": "The daytime things are still there, but changed."},
    # M1
    "M1_A1": {"title": "Draw from the photo", "instruction": "The photo is torn. Use it to draw the place again.", "hint": "Big things first, small things later."},
    "M1_A2": {"title": "Help the robot draw", "instruction": "The robot only remembers this picture. Use it to draw the place for the robot.", "hint": "Find where things are first, then add details."},
    "M1_E3": {"title": "Treasure map", "instruction": "Use the picture to draw where the treasure is hidden, so others can find the place.", "hint": "What is on the left, what is on the right?"},
    "M1_E4": {"title": "The kitten's home", "instruction": "A kitten cannot find its home. Use the picture to draw its home.", "hint": "Place the big things first, then look for details."},
    "M1_E5": {"title": "Complete the puzzle", "instruction": "A large piece of the puzzle is missing. Use the picture to draw the missing part.", "hint": "Look at what connects at the edges."},
    "M1_J3": {"title": "The drone's picture", "instruction": "Draw the place shown in the picture sent by the drone.", "hint": "Overall positions first, then sizes."},
    "M1_J4": {"title": "An old picture", "instruction": "Use this old picture to draw the place as it was.", "hint": "Which things touch, which are apart?"},
    "M1_J5": {"title": "Complete the painting", "instruction": "Half of the painting is missing. Use the original picture to complete it.", "hint": "Keep the original proportions and positions."},
    # M2
    "M2_A1": {"title": "Look around a planet", "instruction": "You arrive on a planet. Draw the things in front of you as they are.", "hint": "Look at sizes, positions, and who is in front of whom."},
    "M2_A2": {"title": "Help the robot see", "instruction": "The robot cannot tell big from small or front from back. Copy the picture to help it see.", "hint": "Draw the sizes, positions and overlaps as in the picture."},
    "M2_E3": {"title": "Toy list", "instruction": "Draw these items in the toy shop as they appear in the picture.", "hint": "Count them, then see where each one sits."},
    "M2_E4": {"title": "Treasure notes", "instruction": "Draw these objects at the treasure site so someone else can put them back in the same positions.", "hint": "Positions matter, and who covers whom."},
    "M2_E5": {"title": "Detective notes", "instruction": "Draw every object at the scene.", "hint": "Draw only the parts you can actually see."},
    "M2_J3": {"title": "Experiment notes", "instruction": "Before the experiment, draw the shapes, sizes, and positions of the objects on the table.", "hint": "Proportions first, then positions and overlaps."},
    "M2_J4": {"title": "Ten-minute drawing", "instruction": "Draw the scene in front of you as it is, within ten minutes.", "hint": "Which object is in front? Who covers whom?"},
    "M2_J5": {"title": "Museum objects", "instruction": "Copy the objects in the picture. Show their sizes and which ones are in front or behind.", "hint": "Proportions, positions and overlaps all count."},
    # M3
    "M3_A1": {"title": "A picture from a dream", "instruction": "These pieces come from a dream. Continue drawing to make a complete picture.", "hint": "A piece can become anything."},
    "M3_A2": {"title": "Turn symbols into a picture", "instruction": "Use these symbols to draw a whole world.", "hint": "Turn a symbol around, or give it a new meaning."},
    "M3_E3": {"title": "What is in the clouds?", "instruction": "These lines look like clouds. Continue drawing to show what is hiding inside.", "hint": "Use only a few pieces if you like, or change what they mean."},
    "M3_E4": {"title": "Finish the drawing", "instruction": "This drawing is not finished. Continue from what is already there and complete it.", "hint": "First see what the pieces look like."},
    "M3_E5": {"title": "A picture from puzzle pieces", "instruction": "Continue drawing from these puzzle pieces to make a new picture.", "hint": "You do not have to put them back the old way."},
    "M3_J3": {"title": "Complete the scene", "instruction": "The camera captured only part of the scene. Continue drawing to show what was happening.", "hint": "Find clues in the pieces first, then decide the story."},
    "M3_J4": {"title": "Wall painting", "instruction": "Only these pieces of a wall painting remain. Continue drawing the story it may have told.", "hint": "Look at the shapes first, then decide what they are in the story."},
    "M3_J5": {"title": "Complete the machine", "instruction": "The plan is torn. Use the lines that remain to draw a new machine.", "hint": "A line can become a structure, or a part."},
    # M4
    "M4_A1": {"title": "Umbrella to submarine", "instruction": "Turn an umbrella into a submarine that can travel under the sea.", "hint": "Which parts of the umbrella can stay?"},
    "M4_A2": {"title": "Change the backpack", "instruction": "Turn a backpack into equipment for exploring. Think about what it can help you do.", "hint": "Which parts of the backpack can stay?"},
    "M4_E3": {"title": "Chair to pet", "instruction": "Turn a chair into a pet that follows you around.", "hint": "Which parts of the chair become the body?"},
    "M4_E4": {"title": "Teapot to rocket", "instruction": "Turn a teapot into a rocket that can fly into space.", "hint": "How can the teapot's shape help?"},
    "M4_E5": {"title": "Clock to car", "instruction": "Turn a clock into a car that can travel through the desert.", "hint": "Which parts of the clock become parts of the car?"},
    "M4_J3": {"title": "Shoe to creature", "instruction": "Turn a shoe into a creature that lives in a huge forest. It must still look partly like a shoe.", "hint": "Which structures stay, which change?"},
    "M4_J4": {"title": "Teapot rescue machine", "instruction": "Turn a teapot into a space rescue machine that can rescue at least two people.", "hint": "Think about the rescue job first, then how to change the shape."},
    "M4_J5": {"title": "Bicycle to mech", "instruction": "Turn a bicycle into a mech robot. Think about what it can do.", "hint": "Which parts of the bicycle become parts of the mech?"},
    # M5
    "M5_A1": {"title": "Castle + jellyfish", "instruction": "Draw a castle and a jellyfish combined into one. It could be a creature or a building.", "hint": "Features of both should still be there."},
    "M5_A2": {"title": "Robot + flower", "instruction": "Combine a robot and a flower to draw a new kind of living thing.", "hint": "Do not just stick the flower on. Let them really grow together."},
    "M5_E3": {"title": "Fox + train", "instruction": "Draw a fox and a train combined into something new. Think about where it will go.", "hint": "Think how each one changes the other."},
    "M5_E4": {"title": "Shark + backpack", "instruction": "Draw a shark and a backpack combined into one.", "hint": "Do not just stick one onto the other."},
    "M5_E5": {"title": "Cake + house", "instruction": "Draw a cake and a house combined into one. Think about who lives inside.", "hint": "Think how the two grow into one."},
    "M5_J3": {"title": "Clock + octopus", "instruction": "Draw a clock and an octopus combined into one.", "hint": "Both should still be recognisable."},
    "M5_J4": {"title": "Subway + dragon", "instruction": "Combine a subway train and a dragon to draw a vehicle.", "hint": "Think how the two structures really connect."},
    "M5_J5": {"title": "Whale + school", "instruction": "Draw a school combined with a whale.", "hint": "Do not just put the school on the whale's back."},
    # M6
    "M6_A1": {"title": "Night", "instruction": "Keep the scene. Change only its colors and light and dark areas to make it nighttime.", "hint": "Night has bright spots too."},
    "M6_A2": {"title": "A scary place", "instruction": "Do not add new monsters. Change only the colors and light and dark areas to make the place a little scary.", "hint": "Where is it bright, where is it dark?"},
    "M6_E3": {"title": "Cold", "instruction": "Keep the things in the picture. Change only the colors to make the place look very cold.", "hint": "Cold colours are not only blue."},
    "M6_E4": {"title": "Lively", "instruction": "Do not add new things. Change only the colors to make the place look lively.", "hint": "Where could it be brighter, with more contrast?"},
    "M6_E5": {"title": "Warm", "instruction": "Keep the things in the picture. Change only the colors to make the place look warm.", "hint": "Warm colours can be light or deep too."},
    "M6_J3": {"title": "Mysterious", "instruction": "Keep the things in the picture. Change only the colors and light and dark areas to make the place feel mysterious, as if it holds a secret.", "hint": "Contrast can be strong or soft."},
    "M6_J4": {"title": "A storm is coming", "instruction": "Try not to add new things. Use color, light and dark, and contrast to show that a storm is coming.", "hint": "How do the sky and the ground change?"},
    "M6_J5": {"title": "Safe and dangerous", "instruction": "Do not add new things. Change only the colors and light and dark areas so one side looks safe and the other looks dangerous.", "hint": "The dividing line does not have to be straight."},
    # M7（step1 = 第一步的概念句；step2 = 第二步）
    "M7_A1": {"title": "Wind", "step1": "Use only lines to show the feeling of wind. Do not draw objects.", "step2": "Do not erase the lines. Look at what they remind you of and keep drawing.", "hint": "Lines can be fast or slow."},
    "M7_A2": {"title": "Speed", "step1": "Use only lines to show the feeling of speed. Do not draw objects.", "step2": "Do not erase the lines. Look at what they remind you of and keep drawing.", "hint": "Direction and spacing change how fast it feels."},
    "M7_E3": {"title": "Rain", "step1": "Use only lines to show the feeling of rain. Do not draw objects.", "step2": "Do not erase the lines. Look at what they remind you of and keep drawing.", "hint": "Dense or sparse: what changes?"},
    "M7_E4": {"title": "Bouncing", "step1": "Use only lines to show the feeling of bouncing. Do not draw objects.", "step2": "Do not erase the lines. Look at what they remind you of and keep drawing.", "hint": "A line can bend, or turn suddenly."},
    "M7_E5": {"title": "Growing", "step1": "Use only lines to show the feeling of growing. Do not draw objects.", "step2": "Do not erase the lines. Look at what they remind you of and keep drawing.", "hint": "You can start from one point."},
    "M7_J3": {"title": "Whispering", "step1": "Use only lines to show the feeling of whispering. Do not draw objects.", "step2": "Do not erase the lines. Build on them to make a picture.", "hint": "How do you draw a light line?"},
    "M7_J4": {"title": "Heavy", "step1": "Use only lines to show the feeling of heaviness. Do not draw objects.", "step2": "Do not erase the lines. Build on them to make a picture.", "hint": "Thick, dense, low: what does that feel like?"},
    "M7_J5": {"title": "Tense", "step1": "Use only lines to show the feeling of tension. Do not draw objects.", "step2": "Do not erase the lines. Build on them to make a picture.", "hint": "Lines can shake, or crowd together."},
    # M8（rules = 规则；challenge = 可选第三条）
    "M8_A1": {"title": "City on the clouds", "instruction": "Draw a day in this world.", "rules": ["Everyone lives on clouds.", "Animals build the houses."]},
    "M8_A2": {"title": "Walking shadows", "instruction": "Draw one thing that happens here at night.", "rules": ["Shadows walk on their own.", "Everything weighs less at night."]},
    "M8_E3": {"title": "People have shrunk", "instruction": "Draw what happens during a day here.", "rules": ["People are smaller than bugs.", "Plants are taller than buildings."]},
    "M8_E4": {"title": "Water in the sky", "instruction": "Draw how everyone lives here.", "rules": ["Water floats in the sky.", "Houses are alive."]},
    "M8_E5": {"title": "A world inside a tree", "instruction": "Draw the busiest place here.", "rules": ["The whole world is inside one tree.", "Machines and plants live together."]},
    "M8_J3": {"title": "Falling sideways", "instruction": "", "rules": ["Things fall sideways instead of down.", "People are smaller than bugs."], "challenge": "Water floats in the sky."},
    "M8_J4": {"title": "Underwater city", "instruction": "", "rules": ["Houses are alive.", "The whole city is underwater."], "challenge": "The ground is a moving island."},
    "M8_J5": {"title": "Animal city", "instruction": "", "rules": ["Animals build cities.", "Plants are bigger than buildings."], "challenge": "Machines and plants live together."},
    # M9
    "M9_A1": {"title": "A new door at school", "instruction": "After school, a new door appears at school. Draw the place behind it.", "hint": "Draw the moment it opens."},
    "M9_A2": {"title": "The thing that did not shrink", "instruction": "Everything in the city has shrunk except one thing. Draw what happens next.", "hint": "First decide which thing stayed the same."},
    "M9_E3": {"title": "A talking desk", "instruction": "Your desk starts talking. Draw the scene and think about what it says.", "hint": "Draw the first moment you hear it."},
    "M9_E4": {"title": "A shark at school", "instruction": "A shark joins your class. Draw what happens next.", "hint": "Where does it sit? What is everyone doing?"},
    "M9_E5": {"title": "A pet's superpower", "instruction": "Draw the day you discover that your pet has a superpower.", "hint": "When did it give itself away?"},
    "M9_J3": {"title": "Something is missing", "instruction": "One thing goes missing from the classroom every day. Draw the day you find a clue.", "hint": "Clues matter more than answers."},
    "M9_J4": {"title": "A store on Mars", "instruction": "Draw a convenience store on Mars. What does it sell? Who shops there?", "hint": "Let the shelves and the customers tell the story."},
    "M9_J5": {"title": "A place on the map", "instruction": "The map shows a place that does not exist in real life. Imagine you find it and draw what it looks like.", "hint": "Leave a clue or two so others can guess what happened here."},
}
M8_LEAD_EN = " Show both of these:"
M8_LEAD_CHALLENGE_EN = "Draw a world with both of these rules:"
M8_CHALLENGE_EN = "Optional: {text}"
M7_STEP1_EN = "Step 1 ({seconds} seconds): {text}"
M7_STEP2_EN = "Step 2: {text}"


def _v2(task: Dict[str, Any]) -> Optional[Dict[str, str]]:
    en = V2_EN.get(task.get("task_id") or "")
    if not en:
        return None
    fam = task.get("family")
    if fam == "M7":
        phases = task.get("phases") or []
        seconds = phases[0]["seconds"] if phases else 60
        text = M7_STEP1_EN.format(seconds=seconds, text=en["step1"]) + "\n" + M7_STEP2_EN.format(text=en["step2"])
        return {"title": en["title"], "instruction": text, "hint": en["hint"]}
    if fam == "M8":
        text = (M8_LEAD_CHALLENGE_EN if en.get("challenge") else en["instruction"] + M8_LEAD_EN) + "\n" + "\n".join(f"· {r}" for r in en["rules"])
        if en.get("challenge"):
            text += "\n" + M8_CHALLENGE_EN.format(text=en["challenge"])
        return {"title": en["title"], "instruction": text, "hint": en.get("hint", "")}
    return {"title": en["title"], "instruction": en["instruction"], "hint": en.get("hint", "")}
