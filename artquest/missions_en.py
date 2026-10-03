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
    "M0_A1": {"title": "A strange superpower", "instruction": "You suddenly have a very strange superpower. Draw what happens the first time you use it.", "hint": "Strange can still be useful."},
    "M0_A2": {"title": "A car with no wheels", "instruction": "Design a vehicle with no wheels. How does it move?", "hint": "First decide how it moves, then what it looks like."},
    "M0_E3": {"title": "Monster restaurant", "instruction": "A restaurant only for monsters. What are they eating?", "hint": "What is on the menu?"},
    "M0_E4": {"title": "Food with a personality", "instruction": "Give a food a personality. How is it feeling today?", "hint": "It can have arms and legs."},
    "M0_E5": {"title": "The final level", "instruction": "Draw the last level of a game. The boss could be an alarm clock.", "hint": "The boss does not have to be a monster."},
    "M0_J3": {"title": "Undersea city", "instruction": "Draw a city under the sea. How do people live there?", "hint": "Where does the light come from?"},
    "M0_J4": {"title": "Machines and plants", "instruction": "A place where a robot and plants live together. Who looks after whom?", "hint": "A machine can grow plants too."},
    "M0_J5": {"title": "The gym at night", "instruction": "At night the gym turns into another world. Draw what you see.", "hint": "The daytime things are still there, but changed."},
    # M1
    "M1_A1": {"title": "The torn photo", "instruction": "The photo is torn. Look at it and draw this place again.", "hint": "Big things first, small things later."},
    "M1_A2": {"title": "The robot's memory", "instruction": "The robot only remembers this one picture. Help it draw the place back.", "hint": "Find where things are first, then add details."},
    "M1_E3": {"title": "Treasure map", "instruction": "This is where the treasure is. Copy it so others can find the place.", "hint": "What is on the left, what is on the right?"},
    "M1_E4": {"title": "The kitten's home", "instruction": "A kitten is lost and only remembers its home looks like this. Draw it from the picture.", "hint": "Place the big things first, then look for details."},
    "M1_E5": {"title": "The last puzzle piece", "instruction": "A big piece of the puzzle is missing. Complete it from this picture.", "hint": "Look at what connects at the edges."},
    "M1_J3": {"title": "Drone lost", "instruction": "The drone sent back only this image before going silent. Draw the location.", "hint": "Overall positions first, then sizes."},
    "M1_J4": {"title": "The dig site", "instruction": "A thousand years from now someone digs up this picture. Help them rebuild the place.", "hint": "Which things touch, which are apart?"},
    "M1_J5": {"title": "The deleted painting", "instruction": "Half of the museum's painting was deleted. Restore it from the original.", "hint": "Keep the original proportions and positions."},
    # M2
    "M2_A1": {"title": "Alien field notes", "instruction": "You have just landed on a planet. Draw what you see, as it is.", "hint": "Look at sizes, positions, and who is in front of whom."},
    "M2_A2": {"title": "Teach the robot to see", "instruction": "The robot cannot tell big from small or front from back. Draw the picture for it.", "hint": "Draw the sizes, positions and overlaps as in the picture."},
    "M2_E3": {"title": "Toy shop list", "instruction": "The owner needs a list. Draw these things as they are.", "hint": "Count them, then see where each one sits."},
    "M2_E4": {"title": "The treasure scene", "instruction": "The treasure is right here. Draw these things so someone else can put them back.", "hint": "Positions matter, and who covers whom."},
    "M2_E5": {"title": "Detective's notebook", "instruction": "You are a young detective. Draw every object at the scene into your notebook.", "hint": "Draw only the parts you can actually see."},
    "M2_J3": {"title": "Lab record", "instruction": "Before the experiment, record the objects on the table: shapes, sizes, and positions.", "hint": "Proportions first, then positions and overlaps."},
    "M2_J4": {"title": "The spy's report", "instruction": "You have ten minutes. Draw this scene and send it back.", "hint": "Which object is in front? Who covers whom?"},
    "M2_J5": {"title": "Museum catalogue", "instruction": "These items need to be catalogued. Draw a picture that shows sizes and depth.", "hint": "Proportions, positions and overlaps all count."},
    # M3
    "M3_A1": {"title": "Pieces of a dream", "instruction": "These pieces fell out of a dream. Turn them into a complete picture.", "hint": "A piece can become anything."},
    "M3_A2": {"title": "Mystery message", "instruction": "Someone left these strange symbols. Turn them into a whole world.", "hint": "Turn a symbol around, or give it a new meaning."},
    "M3_E3": {"title": "Shapes of clouds", "instruction": "These lines look like the edges of clouds. What is hiding inside?", "hint": "Use only a few pieces if you like, or change what they mean."},
    "M3_E4": {"title": "The monster's doodle", "instruction": "A monster ran off halfway through its drawing. Help finish it.", "hint": "First see what the pieces look like."},
    "M3_E5": {"title": "Fallen puzzle pieces", "instruction": "A few puzzle pieces fell here. Use them to make a new picture.", "hint": "You do not have to put them back the old way."},
    "M3_J3": {"title": "The last camera frame", "instruction": "The camera broke and left only these pieces. Draw what was happening.", "hint": "Find clues in the pieces first, then decide the story."},
    "M3_J4": {"title": "Ancient mural", "instruction": "Only these pieces of the mural are left. Draw the story it may have told.", "hint": "Look at the shapes first, then decide what they are in the story."},
    "M3_J5": {"title": "The torn blueprint", "instruction": "The blueprint was torn. Use what is left to complete a new machine.", "hint": "A line can become a structure, or a part."},
    # M4
    "M4_A1": {"title": "Umbrella to submarine", "instruction": "Turn the umbrella into a submarine that can travel under the sea.", "hint": "Which parts of the umbrella can stay?"},
    "M4_A2": {"title": "Backpack to gear", "instruction": "Turn the backpack into a piece of exploring gear. What can it help you do?", "hint": "Which parts of the backpack can stay?"},
    "M4_E3": {"title": "Chair to pet", "instruction": "Turn the chair into a pet that follows you around.", "hint": "Which parts of the chair become the body?"},
    "M4_E4": {"title": "Teapot to rocket", "instruction": "Turn the teapot into a rocket that can fly to space.", "hint": "How can the teapot's shape help?"},
    "M4_E5": {"title": "Clock to desert car", "instruction": "Turn the clock into a car that can drive across the desert.", "hint": "Which parts of the clock become parts of the car?"},
    "M4_J3": {"title": "Creature of the giant forest", "instruction": "Turn a shoe into a creature of the giant forest. It must still look like a shoe.", "hint": "Which structures stay, which change?"},
    "M4_J4": {"title": "Space rescue machine", "instruction": "Build a space rescue machine from a teapot. It must be able to save at least two people.", "hint": "Think about the rescue job first, then how to change the shape."},
    "M4_J5": {"title": "Bicycle mech", "instruction": "Turn the bicycle into a mech. What can it do?", "hint": "Which parts of the bicycle become parts of the mech?"},
    # M5
    "M5_A1": {"title": "Castle + jellyfish", "instruction": "Fuse a castle and a jellyfish into one new thing. It can be a creature or a building.", "hint": "Features of both should still be there."},
    "M5_A2": {"title": "Robot + flower", "instruction": "Fuse a robot and a flower into a new species.", "hint": "Do not just stick the flower on. Let them really grow together."},
    "M5_E3": {"title": "Fox + train", "instruction": "Turn a fox and a train into one new thing. Where is it going?", "hint": "Think how each one changes the other."},
    "M5_E4": {"title": "Shark + backpack", "instruction": "Turn a shark and a backpack into one new thing. Would you dare carry it?", "hint": "Do not just stick one onto the other."},
    "M5_E5": {"title": "Cake + house", "instruction": "Turn a cake and a house into one new thing. Who lives inside?", "hint": "Think how the two grow into one."},
    "M5_J3": {"title": "Clock + octopus", "instruction": "Fuse a clock and an octopus into something new.", "hint": "Both should still be recognisable."},
    "M5_J4": {"title": "Subway + dragon", "instruction": "Fuse a subway train and a dragon into a vehicle.", "hint": "Think how the two structures really connect."},
    "M5_J5": {"title": "Whale + school", "instruction": "Fuse a whale and a school into one place.", "hint": "Do not just put the school on the whale's back."},
    # M6
    "M6_A1": {"title": "Make it night", "instruction": "Keep the scene as it is. Use only colour and light and dark to make it night.", "hint": "Night has bright spots too."},
    "M6_A2": {"title": "A little scary", "instruction": "Do not add monsters. Use only colour and light and dark to make this place a little scary.", "hint": "Where is it bright, where is it dark?"},
    "M6_E3": {"title": "Make it cold", "instruction": "Do not change the things in it. Use only colour to make this place feel very cold.", "hint": "Cold colours are not only blue."},
    "M6_E4": {"title": "Make it lively", "instruction": "Do not add new things. Use only colour to make this place lively.", "hint": "Where could it be brighter, with more contrast?"},
    "M6_E5": {"title": "Make it warm", "instruction": "Do not change the things in it. Use only colour to make this place feel warm.", "hint": "Warm colours can be light or deep too."},
    "M6_J3": {"title": "Mysterious", "instruction": "Do not change the things in the scene. Use only colour and light and dark to make it mysterious.", "hint": "Contrast can be strong or soft."},
    "M6_J4": {"title": "Before the storm", "instruction": "Add as little as possible. Use colour, light and dark, and contrast to show a storm is coming.", "hint": "How do the sky and the ground change?"},
    "M6_J5": {"title": "Two worlds", "instruction": "Do not add new objects. Use only colour and light and dark so one side of the picture is safe and the other dangerous.", "hint": "The dividing line does not have to be straight."},
    # M7（step1 = 第一步的概念句；step2 = 第二步）
    "M7_A1": {"title": "Lines of wind", "step1": "use only lines to draw “wind”.", "step2": "Do not erase. See what the lines look like, and keep drawing from there.", "hint": "Lines can be fast or slow."},
    "M7_A2": {"title": "Lines of speed", "step1": "use only lines to draw “speed”.", "step2": "Do not erase. See what the lines look like, and keep drawing from there.", "hint": "Direction and spacing change how fast it feels."},
    "M7_E3": {"title": "Lines of rain", "step1": "use only lines to draw “rain”.", "step2": "Do not erase. See what the lines look like, and keep drawing from there.", "hint": "Dense or sparse: what changes?"},
    "M7_E4": {"title": "Bouncing lines", "step1": "use only lines to draw “bouncing”.", "step2": "Do not erase. See what the lines look like, and keep drawing from there.", "hint": "A line can bend, or turn suddenly."},
    "M7_E5": {"title": "Growing lines", "step1": "use only lines to draw “growing”.", "step2": "Do not erase. See what the lines look like, and keep drawing from there.", "hint": "You can start from one point."},
    "M7_J3": {"title": "Whisper", "step1": "use only lines to show “whisper”.", "step2": "Keep the lines and develop them into a picture.", "hint": "How do you draw a light line?"},
    "M7_J4": {"title": "Heavy", "step1": "use only lines to show “heavy”.", "step2": "Keep the lines and develop them into a picture.", "hint": "Thick, dense, low: what does that feel like?"},
    "M7_J5": {"title": "Nervous", "step1": "use only lines to show “nervous”.", "step2": "Keep the lines and develop them into a picture.", "hint": "Lines can shake, or crowd together."},
    # M8（rules = 规则；challenge = 可选第三条）
    "M8_A1": {"title": "City on the clouds", "instruction": "Draw how a day goes here.", "rules": ["Everyone lives on the clouds.", "Animals build the houses."]},
    "M8_A2": {"title": "The shadows ran off", "instruction": "Draw one thing that happens at night.", "rules": ["Shadows walk by themselves.", "At night everything gets lighter."]},
    "M8_E3": {"title": "Everything shrank", "instruction": "Draw what happens in one day.", "rules": ["People are smaller than bugs.", "Plants are taller than buildings."]},
    "M8_E4": {"title": "Water in the sky", "instruction": "Draw how everyone lives.", "rules": ["Water floats in the sky.", "Houses are alive."]},
    "M8_E5": {"title": "A world inside a tree", "instruction": "Draw the busiest place here.", "rules": ["The whole world is inside one tree.", "Machines and plants live together."]},
    "M8_J3": {"title": "Sideways gravity", "instruction": "Draw with the two core rules first. If you want a challenge, add the third.", "rules": ["Gravity goes sideways.", "People are smaller than insects."], "challenge": "Water floats in the sky."},
    "M8_J4": {"title": "The living city", "instruction": "Draw with the two core rules first. If you want a challenge, add the third.", "rules": ["Houses are alive.", "The whole city is underwater."], "challenge": "The ground is a moving island."},
    "M8_J5": {"title": "Animal civilisation", "instruction": "Draw with the two core rules first. If you want a challenge, add the third.", "rules": ["Animals build the cities.", "Plants are bigger than buildings."], "challenge": "Machines and plants live together."},
    # M9
    "M9_A1": {"title": "A new door at school", "instruction": "After school, a door nobody has seen before appears. What is behind it?", "hint": "Draw the moment it opens."},
    "M9_A2": {"title": "Only one thing stayed big", "instruction": "Everything in the city shrank, except one thing. Draw what happens.", "hint": "First decide which thing stayed the same."},
    "M9_E3": {"title": "The talking desk", "instruction": "Your desk suddenly starts talking. What does it say?", "hint": "Draw the first moment you hear it."},
    "M9_E4": {"title": "A shark comes to school", "instruction": "A shark joins your class. What happens?", "hint": "Where does it sit? What is everyone doing?"},
    "M9_E5": {"title": "The pet's secret", "instruction": "Your pet has a secret superpower. Draw the day you found out.", "hint": "When did it give itself away?"},
    "M9_J3": {"title": "One thing goes missing every day", "instruction": "Every day something disappears from the classroom. Draw the day you found a clue.", "hint": "Clues matter more than answers."},
    "M9_J4": {"title": "Convenience store on Mars", "instruction": "A convenience store on Mars. Who shops there, and what does it sell?", "hint": "Let the shelves and the customers tell the story."},
    "M9_J5": {"title": "A place that does not exist", "instruction": "The map marks a place that does not exist. Draw the place you finally found.", "hint": "Leave a clue or two so others can guess what happened here."},
}
M8_LEAD_EN = "Design a world where all of these rules are true. "
M7_STEP1_EN = "Step 1 ({seconds} seconds): do not draw any real thing, {text}"
M7_STEP2_EN = "Step 2: {text}"


def _v2(task: Dict[str, Any]) -> Optional[Dict[str, str]]:
    en = V2_EN.get(task.get("task_id") or "")
    if not en:
        return None
    fam = task.get("family")
    if fam == "M7":
        phases = task.get("phases") or []
        seconds = phases[0]["seconds"] if phases else 60
        text = M7_STEP1_EN.format(seconds=seconds, text=en["step1"]) + "\n\n" + M7_STEP2_EN.format(text=en["step2"])
        return {"title": en["title"], "instruction": text, "hint": en["hint"]}
    if fam == "M8":
        text = M8_LEAD_EN + en["instruction"] + "\n\n" + "\n".join(f"· {r}" for r in en["rules"])
        if en.get("challenge"):
            text += f"\nChallenge: {en['challenge']}"
        return {"title": en["title"], "instruction": text, "hint": en.get("hint", "")}
    return {"title": en["title"], "instruction": en["instruction"], "hint": en.get("hint", "")}
