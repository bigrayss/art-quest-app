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
    en: Optional[Dict[str, str]] = None
    if builder is not None:
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
