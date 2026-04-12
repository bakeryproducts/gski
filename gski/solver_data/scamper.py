"""SCAMPER operators and sub-questions."""

OPERATORS = {
    "S": {
        "name": "Substitute",
        "description": "Replace one part of the product, process, or problem with something else",
        "questions": [
            "What materials or ingredients can be swapped?",
            "Can we use different people or a different team?",
            "Can we substitute the rules or the process?",
            "Can we change the shape, color, or texture?",
            "Can we substitute the place or time?",
            "What other technology could we use instead?",
        ],
    },
    "C": {
        "name": "Combine",
        "description": "Merge two or more elements to create something new",
        "questions": [
            "What ideas or parts can be combined?",
            "Can we merge this product with another service?",
            "What happens if we combine several talents or departments?",
            "Can we package these features together?",
            "What if we combined the purposes or objectives?",
            "Can we combine this with something from a different domain?",
        ],
    },
    "A": {
        "name": "Adapt",
        "description": "Adjust an existing idea to fit a new context",
        "questions": [
            "What other ideas are like this one?",
            "Is there something similar in a different field we can copy?",
            "Could we adapt this to a different market or user base?",
            "What could we emulate from nature?",
            "What historical solution could we adapt?",
            "What if we changed the context entirely?",
        ],
    },
    "M": {
        "name": "Modify (Magnify / Minify)",
        "description": "Change attributes — make bigger, smaller, or alter a quality",
        "questions": [
            "What can be exaggerated or magnified?",
            "What can be made smaller, lighter, or faster?",
            "Can we change the frequency or timing?",
            "What if we changed the color or form factor?",
            "What happens if we make it 10x bigger? 10x smaller?",
            "Can we add more features? Remove features?",
        ],
    },
    "P": {
        "name": "Put to another use",
        "description": "Use the existing thing for a different purpose or audience",
        "questions": [
            "Who else could use this?",
            "Can it be used in a different industry?",
            "What other unmet needs can this fulfill?",
            "Could the waste or by-product be useful?",
            "What if children used it? Elderly? Experts? Beginners?",
            "Can this solve a completely different problem?",
        ],
    },
    "E": {
        "name": "Eliminate",
        "description": "Remove unnecessary parts or steps to simplify",
        "questions": [
            "What features or parts are redundant?",
            "Can we eliminate the rules or the middleman?",
            "What would happen if we removed a specific step?",
            "How can we make it more streamlined?",
            "What if we removed the most expensive component?",
            "What's the absolute minimum viable version?",
        ],
    },
    "R": {
        "name": "Rearrange (Reverse)",
        "description": "Change order, reverse the process, or swap components",
        "questions": [
            "What if we did the process in reverse?",
            "Can we swap the roles of participants?",
            "What if we changed the layout or sequence?",
            "What happens if we look at it from the opposite perspective?",
            "Can we transpose cause and effect?",
            "What if the last step came first?",
        ],
    },
}

# Ordered keys for iteration
ORDER = ["S", "C", "A", "M", "P", "E", "R"]
