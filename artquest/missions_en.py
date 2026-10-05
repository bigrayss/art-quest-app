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
    "M0_A1": {"title": "A strange superpower", "instruction": "You suddenly have a very strange superpower. What happens the first time you use it? Draw that moment.", "hint": "Strange can still be useful."},
    "M0_A2": {"title": "A car with no wheels", "instruction": "Design a vehicle without wheels. Think about how it moves.", "hint": "First decide how it moves, then what it looks like."},
    "M0_E3": {"title": "Monster restaurant", "instruction": "Draw a restaurant that serves only monsters. What are they eating?", "hint": "What is on the menu?"},
    "M0_E4": {"title": "Food with a personality", "instruction": "Choose a food and give it a personality in your drawing. How is it feeling today?", "hint": "It can have arms and legs."},
    "M0_E5": {"title": "The final level", "instruction": "Draw the final level of a game. The boss could even be an alarm clock.", "hint": "The boss does not have to be a monster."},
    "M0_J3": {"title": "Undersea city", "instruction": "Draw an underwater city showing how people live there.", "hint": "Where does the light come from?"},
    "M0_J4": {"title": "Machines and plants", "instruction": "Draw a place where a robot and plants live together. Who looks after whom?", "hint": "A machine can grow plants too."},
    "M0_J5": {"title": "The gym at night", "instruction": "At night, the gym becomes another world. Draw what you see.", "hint": "The daytime things are still there, but changed."},
    # M1
    "M1_A1": {"title": "The torn photo", "instruction": "This photo is damaged. Use it to draw the place again.", "hint": "Big things first, small things later."},
    "M1_A2": {"title": "The robot's memory", "instruction": "The robot only remembers this picture. Help it draw the place again.", "hint": "Find where things are first, then add details."},
    "M1_E3": {"title": "Treasure map", "instruction": "The picture shows where the treasure is hidden. Copy it so others can find the place.", "hint": "What is on the left, what is on the right?"},
    "M1_E4": {"title": "The kitten's home", "instruction": "A kitten is lost and only remembers its home as it looks in this picture. Draw its home from the picture.", "hint": "Place the big things first, then look for details."},
    "M1_E5": {"title": "The last puzzle piece", "instruction": "A large piece of the puzzle is missing. Use this picture to fill in the missing part.", "hint": "Look at what connects at the edges."},
    "M1_J3": {"title": "Lost contact with the drone", "instruction": "The drone lost contact after sending this picture. Draw the place shown in it.", "hint": "Overall positions first, then sizes."},
    "M1_J4": {"title": "Archaeological dig", "instruction": "A thousand years from now, someone digs up this picture. Help them reconstruct the place it shows.", "hint": "Which things touch, which are apart?"},
    "M1_J5": {"title": "The deleted painting", "instruction": "Half of a museum painting has been deleted. Restore it using the original image.", "hint": "Keep the original proportions and positions."},
    # M2
    "M2_A1": {"title": "Alien field notes", "instruction": "You have just arrived on a planet. Look closely and draw the things in front of you as they are.", "hint": "Look at sizes, positions, and who is in front of whom."},
    "M2_A2": {"title": "Teach the robot to see", "instruction": "The robot cannot tell big from small or front from back. Copy the picture to help it understand.", "hint": "Draw the sizes, positions and overlaps as in the picture."},
    "M2_E3": {"title": "Toy shop list", "instruction": "The toy shop owner needs a list. Draw these objects as they are.", "hint": "Count them, then see where each one sits."},
    "M2_E4": {"title": "The treasure scene", "instruction": "The treasure is here. Draw these objects so someone else can put them back in their original positions.", "hint": "Positions matter, and who covers whom."},
    "M2_E5": {"title": "Detective's notebook", "instruction": "You are a young detective. Draw every object at the scene in your notebook.", "hint": "Draw only the parts you can actually see."},
    "M2_J3": {"title": "Lab record", "instruction": "Before the experiment begins, draw the shapes, sizes, and relative positions of the objects on the table.", "hint": "Proportions first, then positions and overlaps."},
    "M2_J4": {"title": "The spy's report", "instruction": "You have only ten minutes. Draw this scene and send it back.", "hint": "Which object is in front? Who covers whom?"},
    "M2_J5": {"title": "Museum catalog", "instruction": "These items need to be catalogued. Draw them so their sizes and front-to-back relationships are clear.", "hint": "Proportions, positions and overlaps all count."},
    # M3
    "M3_A1": {"title": "Pieces of a dream", "instruction": "These pieces come from a dream. Build on them to make a complete picture.", "hint": "A piece can become anything."},
    "M3_A2": {"title": "Mystery message", "instruction": "Someone has left these strange symbols. Use them to draw a complete world.", "hint": "Turn a symbol around, or give it a new meaning."},
    "M3_E3": {"title": "Cloud shapes", "instruction": "These lines look like the edges of clouds. What is hiding inside them?", "hint": "Use only a few pieces if you like, or change what they mean."},
    "M3_E4": {"title": "The monster's doodle", "instruction": "A monster ran off halfway through a drawing. Continue from what it left and finish the picture.", "hint": "First see what the pieces look like."},
    "M3_E5": {"title": "Fallen puzzle pieces", "instruction": "A few puzzle pieces have fallen here. Use them to make a new picture.", "hint": "You do not have to put them back the old way."},
    "M3_J3": {"title": "The last camera frame", "instruction": "The security camera left only these fragments before breaking. Draw what was happening.", "hint": "Find clues in the pieces first, then decide the story."},
    "M3_J4": {"title": "Ancient mural", "instruction": "Only these fragments of an ancient mural remain. Draw the story it may once have told.", "hint": "Look at the shapes first, then decide what they are in the story."},
    "M3_J5": {"title": "The torn blueprint", "instruction": "The blueprint has been torn. Use the remaining clues to draw a new machine.", "hint": "A line can become a structure, or a part."},
    # M4
    "M4_A1": {"title": "Umbrella to submarine", "instruction": "Turn the umbrella into a submarine that can travel under the sea.", "hint": "Which parts of the umbrella can stay?"},
    "M4_A2": {"title": "Backpack equipment", "instruction": "Turn the backpack into a piece of exploration equipment. Think about what it can help you do.", "hint": "Which parts of the backpack can stay?"},
    "M4_E3": {"title": "Chair to pet", "instruction": "Turn the chair into a pet that follows you around.", "hint": "Which parts of the chair become the body?"},
    "M4_E4": {"title": "Teapot to rocket", "instruction": "Turn the teapot into a rocket that can fly into space.", "hint": "How can the teapot's shape help?"},
    "M4_E5": {"title": "Clock to desert car", "instruction": "Turn the clock into a vehicle that can travel through the desert.", "hint": "Which parts of the clock become parts of the car?"},
    "M4_J3": {"title": "Creature of the giant forest", "instruction": "Turn a shoe into a creature living in a giant forest, keeping enough of its features for it to be recognizable as a shoe.", "hint": "Which structures stay, which change?"},
    "M4_J4": {"title": "Space rescue machine", "instruction": "Turn the teapot into a space rescue machine that can rescue at least two people.", "hint": "Think about the rescue job first, then how to change the shape."},
    "M4_J5": {"title": "Bicycle mech", "instruction": "Turn the bicycle into a mech. Think about what it can do.", "hint": "Which parts of the bicycle become parts of the mech?"},
    # M5
    "M5_A1": {"title": "Castle + jellyfish", "instruction": "Combine a castle and a jellyfish into something new. It can be a creature or a building.", "hint": "Features of both should still be there."},
    "M5_A2": {"title": "Robot + flower", "instruction": "Fuse a robot and a flower into a new species.", "hint": "Do not just stick the flower on. Let them really grow together."},
    "M5_E3": {"title": "Fox + train", "instruction": "Combine a fox and a train into something new. Where will it go?", "hint": "Think how each one changes the other."},
    "M5_E4": {"title": "Shark + backpack", "instruction": "Combine a shark and a backpack into something new. Would you dare carry it on your back?", "hint": "Do not just stick one onto the other."},
    "M5_E5": {"title": "Cake + house", "instruction": "Combine a cake and a house into something new. Who might live inside?", "hint": "Think how the two grow into one."},
    "M5_J3": {"title": "Clock + octopus", "instruction": "Fuse a clock and an octopus into something new.", "hint": "Both should still be recognisable."},
    "M5_J4": {"title": "Subway + dragon", "instruction": "Fuse a subway train and a dragon into a vehicle.", "hint": "Think how the two structures really connect."},
    "M5_J5": {"title": "Whale + school", "instruction": "Fuse a whale and a school into one place.", "hint": "Do not just put the school on the whale's back."},
    # M6
    "M6_A1": {"title": "Make it night", "instruction": "Keep the original scene. Change only its colors and light and dark areas to make it nighttime.", "hint": "Night has bright spots too."},
    "M6_A2": {"title": "A little scary", "instruction": "Do not add new monsters. Use only color and light and dark to make this place a little scary.", "hint": "Where is it bright, where is it dark?"},
    "M6_E3": {"title": "Make it cold", "instruction": "Keep the objects already in the picture. Use only color to make the place feel very cold.", "hint": "Cold colours are not only blue."},
    "M6_E4": {"title": "Make it lively", "instruction": "Do not add anything new. Use only color to make this place feel lively.", "hint": "Where could it be brighter, with more contrast?"},
    "M6_E5": {"title": "Make it warm", "instruction": "Keep the objects already in the picture. Use only color to make the place feel warm.", "hint": "Warm colours can be light or deep too."},
    "M6_J3": {"title": "Mysterious", "instruction": "Do not change the objects in the scene. Use only color and light and dark to make the place feel mysterious.", "hint": "Contrast can be strong or soft."},
    "M6_J4": {"title": "Before the storm", "instruction": "Keep new objects to a minimum. Use color, light and dark, and contrast to show that a storm is approaching.", "hint": "How do the sky and the ground change?"},
    "M6_J5": {"title": "Two worlds", "instruction": "Do not add new objects. Use only color and light and dark to make one side of the picture feel safe and the other feel dangerous.", "hint": "The dividing line does not have to be straight."},
    # M7（step1 = 第一步的概念句；step2 = 第二步）
    "M7_A1": {"title": "Lines of wind", "step1": "Use only lines to suggest \"wind\". Do not draw specific objects.", "step2": "Do not erase the lines. Look at what they suggest and keep drawing from them.", "hint": "Lines can be fast or slow."},
    "M7_A2": {"title": "Lines of speed", "step1": "Use only lines to suggest \"speed\". Do not draw specific objects.", "step2": "Do not erase the lines. Look at what they suggest and keep drawing from them.", "hint": "Direction and spacing change how fast it feels."},
    "M7_E3": {"title": "Lines of rain", "step1": "Use only lines to draw \"rain\". Do not draw specific objects.", "step2": "Do not erase the lines. Look at what they suggest and keep drawing from them.", "hint": "Dense or sparse: what changes?"},
    "M7_E4": {"title": "Bouncing lines", "step1": "Use only lines to suggest \"bouncing\". Do not draw specific objects.", "step2": "Do not erase the lines. Look at what they suggest and keep drawing from them.", "hint": "A line can bend, or turn suddenly."},
    "M7_E5": {"title": "Growing lines", "step1": "Use only lines to suggest \"growth\". Do not draw specific objects.", "step2": "Do not erase the lines. Look at what they suggest and keep drawing from them.", "hint": "You can start from one point."},
    "M7_J3": {"title": "Whisper", "step1": "Use only lines to express \"whispering\". Do not draw specific objects.", "step2": "Keep the lines and develop them into a picture.", "hint": "How do you draw a light line?"},
    "M7_J4": {"title": "Heavy", "step1": "Use only lines to express \"heaviness\". Do not draw specific objects.", "step2": "Keep the lines and develop them into a picture.", "hint": "Thick, dense, low: what does that feel like?"},
    "M7_J5": {"title": "Nervous", "step1": "Use only lines to express \"tension\". Do not draw specific objects.", "step2": "Keep the lines and develop them into a picture.", "hint": "Lines can shake, or crowd together."},
    # M8（rules = 规则；challenge = 可选第三条）
    "M8_A1": {"title": "City on the clouds", "instruction": "showing a day in its life.", "rules": ["Everyone lives on clouds.", "Animals build the houses."]},
    "M8_A2": {"title": "The shadows ran off", "instruction": "showing one event that happens at night.", "rules": ["Shadows walk on their own.", "Everything becomes lighter in weight at night."]},
    "M8_E3": {"title": "Everything shrank", "instruction": "showing what happens during a day.", "rules": ["People are smaller than bugs.", "Plants are taller than buildings."]},
    "M8_E4": {"title": "Water in the sky", "instruction": "showing how everyone lives.", "rules": ["Water floats in the sky.", "Houses are alive."]},
    "M8_E5": {"title": "A world inside a tree", "instruction": "showing its liveliest place.", "rules": ["The whole world is inside a tree.", "Machines and plants live together."]},
    "M8_J3": {"title": "Sideways gravity", "instruction": "Draw a world that follows the two core rules below. For an extra challenge, you can add the third rule.", "rules": ["Gravity acts sideways.", "People are smaller than insects."], "challenge": "Water floats in the sky."},
    "M8_J4": {"title": "The living city", "instruction": "Draw a world that follows the two core rules below. For an extra challenge, you can add the third rule.", "rules": ["Houses are alive.", "The entire city is underwater."], "challenge": "The ground is a moving island."},
    "M8_J5": {"title": "Animal civilization", "instruction": "Draw a world that follows the two core rules below. For an extra challenge, you can add the third rule.", "rules": ["Animals build cities.", "Plants are bigger than buildings."], "challenge": "Machines and plants live together."},
    # M9
    "M9_A1": {"title": "A new door at school", "instruction": "After school, a door no one has seen before appears in the school. What place is behind it?", "hint": "Draw the moment it opens."},
    "M9_A2": {"title": "Only one thing stayed big", "instruction": "Everything in the city has shrunk except one thing. Draw what happens next.", "hint": "First decide which thing stayed the same."},
    "M9_E3": {"title": "The talking desk", "instruction": "Your desk suddenly starts talking. What does it say?", "hint": "Draw the first moment you hear it."},
    "M9_E4": {"title": "A shark comes to school", "instruction": "A shark joins your class. What happens next?", "hint": "Where does it sit? What is everyone doing?"},
    "M9_E5": {"title": "The pet's secret", "instruction": "Your pet has a secret superpower. Draw the day you discover it.", "hint": "When did it give itself away?"},
    "M9_J3": {"title": "One thing goes missing every day", "instruction": "Something goes missing from the classroom every day. Draw the day you find a clue.", "hint": "Clues matter more than answers."},
    "M9_J4": {"title": "Convenience store on Mars", "instruction": "Draw a convenience store on Mars. Who shops there, and what does it sell?", "hint": "Let the shelves and the customers tell the story."},
    "M9_J5": {"title": "A place that does not exist", "instruction": "The map shows a place that does not exist. You finally find it. Draw what it looks like.", "hint": "Leave a clue or two so others can guess what happened here."},
}
M8_LEAD_EN = "Draw a world where both rules below are true, "
M8_CHALLENGE_EN = "Optional challenge: {text}"
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
        text = ("" if en.get("challenge") else M8_LEAD_EN) + en["instruction"] + "\n" + "\n".join(f"· {r}" for r in en["rules"])
        if en.get("challenge"):
            text += "\n" + M8_CHALLENGE_EN.format(text=en["challenge"])
        return {"title": en["title"], "instruction": text, "hint": en.get("hint", "")}
    return {"title": en["title"], "instruction": en["instruction"], "hint": en.get("hint", "")}
