###############################################################################
# Gemini API - Nano Banana Image Generation - Python Code Samples
# Source: https://ai.google.dev/gemini-api/docs/image-generation
###############################################################################


# =============================================================================
# 1. Image generation (text-to-image)
# =============================================================================

from google import genai
from google.genai import types
from PIL import Image

client = genai.Client()

prompt = ("Create a picture of a nano banana dish in a fancy restaurant with a Gemini theme")
response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[prompt],
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image.save("generated_image.png")


# =============================================================================
# 2. Image editing (text-and-image-to-image)
# =============================================================================

from google import genai
from google.genai import types
from PIL import Image

client = genai.Client()

prompt = (
    "Create a picture of my cat eating a nano-banana in a "
    "fancy restaurant under the Gemini constellation",
)

image = Image.open("/path/to/cat_image.png")

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[prompt, image],
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image.save("generated_image.png")


# =============================================================================
# 3. Multi-turn image editing
# =============================================================================

from google import genai
from google.genai import types

client = genai.Client()

chat = client.chats.create(
    model="gemini-3-pro-image-preview",
    config=types.GenerateContentConfig(
        response_modalities=['TEXT', 'IMAGE'],
        tools=[{"google_search": {}}]
    )
)

message = "Create a vibrant infographic that explains photosynthesis as if it were a recipe for a plant's favorite food. Show the \"ingredients\" (sunlight, water, CO2) and the \"finished dish\" (sugar/energy). The style should be like a page from a colorful kids' cookbook, suitable for a 4th grader."

response = chat.send_message(message)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image:= part.as_image():
        image.save("photosynthesis.png")


# =============================================================================
# 4. Multi-turn image editing (continued - change language to Spanish)
# =============================================================================

message = "Update this infographic to be in Spanish. Do not change any other elements of the image."
aspect_ratio = "16:9" # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
resolution = "2K" # "1K", "2K", "4K"

response = chat.send_message(message,
    config=types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=resolution
        ),
    ))

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image:= part.as_image():
        image.save("photosynthesis_spanish.png")


# =============================================================================
# 5. Use up to 14 reference images
# =============================================================================

from google import genai
from google.genai import types
from PIL import Image

prompt = "An office group photo of these people, they are making funny faces."
aspect_ratio = "5:4" # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
resolution = "2K" # "1K", "2K", "4K"

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=[
        prompt,
        Image.open('person1.png'),
        Image.open('person2.png'),
        Image.open('person3.png'),
        Image.open('person4.png'),
        Image.open('person5.png'),
    ],
    config=types.GenerateContentConfig(
        response_modalities=['TEXT', 'IMAGE'],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=resolution
        ),
    )
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image:= part.as_image():
        image.save("office.png")


# =============================================================================
# 6. Grounding with Google Search
# =============================================================================

from google import genai
prompt = "Visualize the current weather forecast for the next 5 days in San Francisco as a clean, modern weather chart. Add a visual on what I should wear each day"
aspect_ratio = "16:9" # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_modalities=['Text', 'Image'],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
        ),
        tools=[{"google_search": {}}]
    )
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image:= part.as_image():
        image.save("weather.png")


# =============================================================================
# 7. Generate images up to 4K resolution
# =============================================================================

from google import genai
from google.genai import types

prompt = "Da Vinci style anatomical sketch of a dissected Monarch butterfly. Detailed drawings of the head, wings, and legs on textured parchment with notes in English." 
aspect_ratio = "1:1" # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
resolution = "1K" # "1K", "2K", "4K"

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_modalities=['TEXT', 'IMAGE'],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=resolution
        ),
    )
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image:= part.as_image():
        image.save("butterfly.png")


# =============================================================================
# 8. Thinking Process
# =============================================================================

for part in response.parts:
    if part.thought:
        if part.text:
            print(part.text)
        elif image:= part.as_image():
            image.show()


# =============================================================================
# Prompt Templates
# =============================================================================


# --- 1. Photorealistic scenes ---
# A photorealistic [shot type] of [subject], [action or expression], set in
# [environment]. The scene is illuminated by [lighting description], creating
# a [mood] atmosphere. Captured with a [camera/lens details], emphasizing
# [key textures and details]. The image should be in a [aspect ratio] format.


# --- 2. Stylized illustrations & stickers ---
# A [style] sticker of a [subject], featuring [key characteristics] and a
# [color palette]. The design should have [line style] and [shading style].
# The background must be transparent.


# --- 3. Accurate text in images ---
# Create a [image type] for [brand/concept] with the text "[text to render]"
# in a [font style]. The design should be [style description], with a
# [color scheme].


# --- 4. Product mockups & commercial photography ---
# A high-resolution, studio-lit product photograph of a [product description]
# on a [background surface/description]. The lighting is a [lighting setup,
# e.g., three-point softbox setup] to [lighting purpose]. The camera angle is
# a [angle type] to showcase [specific feature]. Ultra-realistic, with sharp
# focus on [key detail]. [Aspect ratio].


# --- 5. Minimalist & negative space design ---
# A minimalist composition featuring a single [subject] positioned in the
# [bottom-right/top-left/etc.] of the frame. The background is a vast, empty
# [color] canvas, creating significant negative space. Soft, subtle lighting.
# [Aspect ratio].


# --- 6. Sequential art (Comic panel / Storyboard) ---
# Make a 3 panel comic in a [style]. Put the character in a [type of scene].


# --- 7. Grounding with Google Search (prompt template) ---
# Make a simple but stylish graphic of last night's Arsenal game in the Champion's League


# =============================================================================
# Image Editing Prompt Templates
# =============================================================================


# --- 1. Adding and removing elements ---
# Using the provided image of [subject], please [add/remove/modify] [element]
# to/from the scene. Ensure the change is [description of how the change should
# integrate].


# --- 2. Inpainting (Semantic masking) ---
# Using the provided image, change only the [specific element] to [new
# element/description]. Keep everything else in the image exactly the same,
# preserving the original style, lighting, and composition.


# --- 3. Style transfer ---
# Transform the provided photograph of [subject] into the artistic style of
# [artist/art style]. Preserve the original composition but render it with
# [description of stylistic elements].


# --- 4. Advanced composition: Combining multiple images ---
# Create a new image by combining the elements from the provided images. Take
# the [element from image 1] and place it with/on the [element from image 2].
# The final image should be a [description of the final scene].


# --- 5. High-fidelity detail preservation ---
# Using the provided images, place [element from image 2] onto [element from
# image 1]. Ensure that the features of [element from image 1] remain
# completely unchanged. The added element should [description of how the
# element should integrate].


# --- 6. Bring something to life ---
# Turn this rough [medium] sketch of a [subject] into a [style description]
# photo. Keep the [specific features] from the sketch but add [new details/materials].


# --- 7. Character consistency: 360 view ---
# A studio portrait of [person] against [background], [looking forward/in profile looking right/etc.]


# =============================================================================
# 9. Output types (image-only response)
# =============================================================================

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[prompt],
    config=types.GenerateContentConfig(
        response_modalities=['Image']
    )
)


# =============================================================================
# 10. Aspect ratios and image size
# =============================================================================

# For gemini-2.5-flash-image
response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[prompt],
    config=types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio="16:9",
        )
    )
)

# For gemini-3-pro-image-preview
response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=[prompt],
    config=types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio="16:9",
            image_size="2K",
        )
    )
)
