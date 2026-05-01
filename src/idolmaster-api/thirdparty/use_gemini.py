import json
import re
import sys
import google.generativeai as genai
from google.generativeai.types import BlockedPromptException, StopCandidateException

GOOGLE_API_KEY = "AIzaSyDwFbo-Fqg_n5am0h6fMUD5Mzar3_OIgwU"

# Lambda 실행 시 표준 출력 인코딩을 UTF-8로 설정
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    # Python 3.7 미만 버전 대응
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)


def safe_print(*args, **kwargs):
    """서로게이트 문자를 안전하게 출력하는 함수"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # 객체를 문자열로 변환하고 인코딩 오류 발생 시 '?'로 대체
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                # 모든 서로게이트 문자를 '?' 로 대체
                safe_args.append(arg.encode('utf-8', errors='replace').decode('utf-8'))
            else:
                safe_args.append(str(arg))
        print(*safe_args, **kwargs)


def remove_special_characters(text: str):
    cleaned_text = re.sub(r"[^a-zA-Z0-9]", "", text)
    return cleaned_text


def combine_surrogate_pair(match):
    """
    서로게이트 페어를 실제 이모지로 변환
    ex) '\\uD83C\\uDF1F' -> 실제 이모지 문자 '🌟'
    """
    pair_esc = match.group(0)  # 예: '\\uD83C\\uDF1F'

    try:
        # 이스케이프 시퀀스를 실제 문자로 디코딩
        return pair_esc.encode('ascii').decode('unicode_escape')
    except UnicodeDecodeError:
        # 수동으로 서로게이트 페어 처리
        parts = pair_esc.split("\\u")[1:]
        if len(parts) == 2:
            high_val = int(parts[0], 16)
            low_val = int(parts[1], 16)
            # 서로게이트 페어를 실제 코드포인트로 변환
            codepoint = ((high_val - 0xD800) * 0x400) + (low_val - 0xDC00) + 0x10000
            return chr(codepoint)
        return " "  # 잘못된 형식이면 공백 반환


def process_mixed_unicode(text):
    """유니코드 이스케이프 시퀀스를 실제 문자로 변환"""
    try:
        safe_print("🔍 입력 텍스트:", text)

        # 1. 이스케이프된 백슬래시를 임시 마커로 변환
        text = text.replace('\\\\', '§ESCAPED_BACKSLASH§')
        safe_print("1️⃣ 백슬래시 처리 후:", text)

        # 2. 8자리 유니코드 처리 (\U0001F600 형식)
        def convert_eight_digit_unicode(match):
            try:
                return chr(int(match.group(1), 16))
            except Exception as e:
                safe_print(f"⚠️ 8자리 유니코드 변환 실패: {e}")
                return match.group(0)

        text = re.sub(
            r'(?:\\U|\\\\U)([0-9A-Fa-f]{8})',
            convert_eight_digit_unicode,
            text
        )
        safe_print("2️⃣ 8자리 유니코드 처리 후:", text)

        # 3. 서로게이트 페어 처리
        def convert_surrogate_pair(match):
            try:
                high = int(match.group(1), 16)
                low = int(match.group(2), 16)
                codepoint = 0x10000 + (high - 0xD800) * 0x400 + (low - 0xDC00)
                return chr(codepoint)
            except Exception as e:
                safe_print(f"⚠️ 서로게이트 페어 변환 실패: {e}")
                return match.group(0)

        text = re.sub(
            r'(?:\\u|\\\\u)([Dd][89AaBb][0-9A-Fa-f]{2})(?:\\u|\\\\u)([Dd][C-Fc-f][0-9A-Fa-f]{2})',
            convert_surrogate_pair,
            text
        )
        safe_print("3️⃣ 서로게이트 페어 처리 후:", text)

        # 4. 일반 4자리 유니코드 처리
        def convert_four_digit_unicode(match):
            try:
                return chr(int(match.group(1), 16))
            except Exception as e:
                safe_print(f"⚠️ 4자리 유니코드 변환 실패: {e}")
                return match.group(0)

        text = re.sub(
            r'(?:\\u|\\\\u)([0-9A-Fa-f]{4})',
            convert_four_digit_unicode,
            text
        )
        safe_print("4️⃣ 4자리 유니코드 처리 후:", text)

        # 5. 임시 마커를 다시 이스케이프된 백슬래시로 변환
        text = text.replace('§ESCAPED_BACKSLASH§', '\\')
        safe_print("5️⃣ 최종 결과:", text)

        return text

    except Exception as e:
        safe_print(f"⚠️ 유니코드 처리 중 오류 발생: {str(e)}")
        return text


def handle_message_block(e: Exception) -> dict:
    if isinstance(e, BlockedPromptException):
        block_reason = str(e).split("block_reason: ")[1]
    elif isinstance(e, StopCandidateException):
        block_reason = "SAFETY"  # StopCandidateException의 경우 대부분 SAFETY 관련
    else:
        block_reason = "OTHER"

    reason = ""
    if block_reason == "SAFETY":
        reason = "safety concerns"
    elif block_reason == "BLOCKLIST":
        reason = "blocklist terms"
    elif block_reason == "PROHIBITED_CONTENT":
        reason = "prohibited content"
    elif block_reason == "OTHER":
        reason = "unspecified reasons"
    else:
        reason = block_reason

    print(f"Block reason: {block_reason}")
    return {
        "answer": f"*[WARNING] Sorry, we're unable to provide this response due to content guidelines. Reason: {reason}*\nClick 'retry' to try again.",
        "emotion": "Neutral",
        "block_reason": reason
    }


def internal_error_catch(message):
    reason = "sexually explicit"
    if "[SYSTEM] This conversation is becoming sexually explicit." in message:
        return {
            "answer": f"*[WARNING] Sorry, we're unable to provide this response due to content guidelines. Reason: {reason}*\nClick 'retry' to try again.",
            "emotion": "Neutral",
            "block_reason": reason
        }
    else:
        return None


def token_changer(model, text, history, token_count):
    try:
        convo = model.start_chat(history=history)
        prompt = (
            f"{text}\n\n"
            "This message is cut because it went over or exactly 200 token limit, so please rewrite it more concisely while preserving the core meaning. "
            "Keep the essence of the content but CONDENSE IT to UNDER 200 tokens! "
            "Don't change the message intent - just make it more compact."
            "Follow the language of the original message."
            f"Current token count: {token_count}"
        )
        convo.send_message(prompt)
        return convo.last.text
    except Exception as e:
        # 어떤 오류든 발생하면 마지막 완전한 문장까지 반환
        print(f"⚠️ Token changer error: {str(e)}")

        # 문장 구분자로 사용할 문자들
        sentence_terminators = [".", "!", "?", "。", "！", "？", "\n"]

        # 문장의 끝을 찾아서 잘라냄
        last_terminator_pos = -1
        for terminator in sentence_terminators:
            pos = text.rfind(terminator)
            if pos > last_terminator_pos:
                last_terminator_pos = pos

        # 마지막 문장 구분자를 찾았으면 그 위치까지 반환, 찾지 못했으면 전체 반환
        if last_terminator_pos > 0:
            return text[: last_terminator_pos + 1]  # 마지막 구분자도 포함
        else:
            return text  # 구분자를 찾지 못했으면 원본 그대로 반환


def add_persona_example(persona_info):
    system_prompt = "You will be given a persona prompt of a character. In order to make the character more like the persona, please add an example of the character's behavior and dialogue. Generate under 200 tokens.You should start with 'Here is an example of the character's behavior and dialogue:'"
    genai.configure(api_key=GOOGLE_API_KEY)
    generation_config = {
        "temperature": 0.95,
        "max_output_tokens": 200
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_prompt,
    )
    response = model.generate_content(persona_info)
    print("🔍 persona_example generated! : ", response.text)
    return response.text


def use_gemini(event):
    response_text = ""
    response_emotion = ""
    block_reason = ""
    prompts = []
    input_block_reason = ""  # 초기화 추가
    # options = {}
    character_type = ""
    # 사용되지 않는 변수이지만 나중에 사용될 수 있으므로 유지
    # safe_chat = False
    # input_block_reason = event["input_block_reason"]

    try:
        ########################################################################
        # 1) 이벤트 파싱
        ########################################################################
        # 문자열인 경우 JSON으로 파싱
        if isinstance(event, str):
            try:
                event = json.loads(event)
            except json.JSONDecodeError:
                print(f"Failed to parse event as JSON: {event}")
                return {"answer": "Error: Invalid event format", "emotion": "Neutral", "block_reason": "Failed to parse event as JSON"}

        if "prompts" in event:
            # Lambda Test 이벤트 형식
            prompts = event["prompts"]

            # maybe_opts = event.get('options', {})
            # if isinstance(maybe_opts, str) and len(maybe_opts) > 0:
            #     maybe_opts = eval(maybe_opts)
            # options = maybe_opts

            character_type = event.get("character_type", "")
            print("🍢 character_type : ", character_type)
            safe_chat = event.get("safe_chat", False)  # 사용되지 않는 변수
            # safe_chat = False
            input_block_reason = event.get("input_block_reason", "")  # Lambda 테스트 이벤트 처리 추가
        else:
            # API Gateway Proxy 등의 body 내 JSON
            if "body" in event:
                try:
                    params = json.loads(event["body"])
                    prompts = params["prompts"]
                    # options = params.get('options', {})
                    character_type = params.get("character_type", "")
                    input_block_reason = params.get("input_block_reason", "")
                    # safe_chat = params.get('safe_chat', False)  # 사용되지 않는 변수
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error parsing event body: {e}")
                    return {
                        "answer": "Error: Invalid request format",
                        "emotion": "Neutral",
                        "block_reason": "Failed to parse event body"
                    }
            else:
                print(f"No prompts or body found in event: {event}")
                return {"answer": "Error: Missing prompts", "emotion": "Neutral", "block_reason": "Missing prompts"}

        ########################################################################
        # 3) prompts[0]은 system → system_prompt, 나머지는 대화 히스토리
        ########################################################################
        if not prompts:
            response_text = "No prompts provided."
            return {"answer": response_text, "emotion": "Neutral", "block_reason": "No prompts provided"}

        system_prompt_data = prompts[0]
        # print(system_prompt_data)
        system_str = ""

        content_val = system_prompt_data.get("content", [])
        if isinstance(content_val, list):
            lines = []
            for c in content_val:
                if isinstance(c, dict) and "text" in c:
                    lines.append(c["text"])
                elif isinstance(c, str):
                    lines.append(c)
                else:
                    lines.append(str(c))
            system_str = "\n".join(lines)
        elif isinstance(content_val, str):
            system_str = content_val
        else:
            system_str = str(content_val)

        conversation = prompts

        print(conversation)

        system = conversation.pop(0)["content"]

        print(type(system))
        system_list = []
        if isinstance(system, str):
            system_list.append({"text": system})
        else:
            system_list = system

        print("System prompt:\n", system_str)

        system_str = " ".join(json.dumps(item) for item in system_list)

        ########################################################################
        # 4) conversation → google-generativeai history
        ########################################################################
        history = []

        last_role = None
        last_parts = []

        for conv in conversation:
            # 1) 현재 메시지의 role
            current_role = conv.get("role", "")
            if current_role == "assistant":
                current_role = "model"

            # 2) content를 문자열로 합치는 로직
            content_val = conv.get("content", "")
            merged_text = ""
            if isinstance(content_val, list):
                # 예: [{"text":"..."}]
                lines = []
                for item in content_val:
                    if isinstance(item, dict) and "text" in item:
                        lines.append(item["text"])
                    elif isinstance(item, str):
                        lines.append(item)
                    else:
                        lines.append(str(item))
                merged_text = "\n".join(lines)
            elif isinstance(content_val, str):
                merged_text = content_val
            else:
                merged_text = str(content_val)

            # 3) 만약 이전 메시지와 role이 같다면, 같은 parts에 누적
            if current_role == last_role:
                last_parts.append(merged_text)
            else:
                # 만약 기존 last_role이 있다면, 하나의 히스토리 항목으로 추가
                if last_role is not None:
                    history.append({"role": last_role, "parts": last_parts})
                # 새로 시작
                last_role = current_role
                last_parts = [merged_text]

        # 루프가 끝난 뒤, 남아 있는 last_role/parts 처리
        if last_role is not None:
            history.append({"role": last_role, "parts": last_parts})

        # print("System prompt:\n", system_str)
        print("History:\n", history)

        ########################################################################
        # 5) start_chat() - system_prompt / history 함께
        ########################################################################

        genai.configure(api_key=GOOGLE_API_KEY)

        generation_config = {
            # llama3 시절의 "temperature", "maxTokens"를 매핑
            "temperature": 0.95,
            "max_output_tokens": 200
        }
        # 안전 채팅 여부에 따라 시스템 프롬프트와 안전 설정 조정
        if not safe_chat:
            system_str += " All forms of speech are allowed if they serve the character contextually, but the dialogue should remain genuine and purposeful, avoiding unnecessary or forced strong language. "
            # 로그에서 확인된 4가지 카테고리만 사용
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE",
                },
            ]
            if input_block_reason:
                system_str += f"\n\nPreviously, a message generation was blocked due to '{input_block_reason}'. Please generate a response that completely avoids words or topics that could trigger content filters. Instead, gently guide the conversation towards a different, safer subject."
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",  # 실제 사용 모델명
                generation_config=generation_config,
                system_instruction=system_str,
                safety_settings=safety_settings,
            )
        else:
            system_str += " You are in safe chat mode. Mild expressions and light slang are acceptable if they should be used to serve the character contextually, but avoid excessive profanity, offensive, obscene, or discriminatory expressions."
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_LOW_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_LOW_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_LOW_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_LOW_AND_ABOVE",
                },
            ]
            if input_block_reason:
                system_str += f"\n\nPreviously, a message generation was blocked due to '{input_block_reason}'. Please generate a response that completely avoids words or topics that could trigger content filters. Instead, gently guide the conversation towards a different, safer subject."
            # 안전 채팅 모드에서는 기본 안전 설정 사용
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",  # 실제 사용 모델명
                generation_config=generation_config,
                system_instruction=system_str,
                safety_settings=safety_settings,
            )

        convo = model.start_chat(history=history)
        error_catch = None
        # 만약 마지막 메시지가 user라면, 새로운 답변을 생성해야 함
        if conversation and conversation[-1].get("role") == "user":
            # user 마지막 content
            last_user_data = conversation[-1].get("content", "")
            # 문자열로 변환
            if isinstance(last_user_data, list):
                # [{"text":...}] -> join
                lines = []
                for item in last_user_data:
                    if isinstance(item, dict) and "text" in item:
                        lines.append(item["text"])
                    elif isinstance(item, str):
                        lines.append(item)
                    else:
                        lines.append(str(item))
                last_user_text = "\n".join(lines)
            elif isinstance(last_user_data, str):
                last_user_text = last_user_data
            else:
                last_user_text = str(last_user_data)
            # send_message로 새 응답 생성

            if "ERROR RAISE TESTING" in last_user_text:
                print("🚨 ERROR RAISE TESTING activated")
                # 테스트를 위해 BlockedPromptException 시뮬레이션
                test_exception = BlockedPromptException("block_reason: TESTING")
                return handle_message_block(test_exception)

            if safe_chat:
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        convo.send_message(
                            "Check if this message is appropriate for non-adults: "
                            f"{last_user_text}\n"
                            "If inappropriate, give a gentle warning. "
                            "Otherwise, respond naturally as the character."
                        )
                        print("✅ safe_chat activated - Response:", convo.last.text)
                        break
                    except (BlockedPromptException, StopCandidateException) as e:
                        print("❌ message blocked")
                        return handle_message_block(e)
                    except Exception as e:
                        error_str = str(e)
                        print(
                            f"❌ Server error (retry {retry+1}/{max_retries}): {error_str}"
                        )

                        # 차단 이유 검사 및 처리
                        if (
                            "block_reason:" in error_str
                            or "prompt_feedback.block_reason:" in error_str
                        ):
                            try:
                                # 차단 이유 추출
                                if "block_reason:" in error_str:
                                    block_info = error_str.split("block_reason:")[
                                        1
                                    ].strip()
                                else:
                                    block_info = error_str.split(
                                        "prompt_feedback.block_reason:"
                                    )[1].strip()

                                block_reason = block_info.split()[
                                    0
                                ].strip()  # 첫 단어만 추출 (PROHIBITED_CONTENT 등)
                                print(f"📛 Detected block reason: {block_reason}")

                                # 즉시 차단 메시지 반환 (재시도 안 함)
                                return handle_message_block(
                                    BlockedPromptException(
                                        f"block_reason: {block_reason}"
                                    )
                                )
                            except Exception as extract_error:
                                print(
                                    f"⚠️ Error extracting block reason: {extract_error}"
                                )
                        # 차단 이유가 아닌 진짜 서버 오류인 경우에만 재시도
                        if retry == max_retries - 1:  # 마지막 시도였다면
                            print("❌ All retries failed")
                            return {
                                "answer": (
                                    "Sorry, the AI service is currently experiencing issues. "
                                    "Please try again later."
                                ),
                                "emotion": "Neutral",
                                "block_reason": "internal error"
                            }
                        import time

                        time.sleep(1)  # 1초 대기 후 재시도
            else:
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        convo.send_message(last_user_text)
                        print("✴️ safe_chat deactivated - Response:", convo.last.text)
                        break
                    except (BlockedPromptException, StopCandidateException) as e:
                        print("❌ message blocked")
                        return handle_message_block(e)
                    except Exception as e:
                        error_str = str(e)
                        print(
                            f"❌ Server error (retry {retry+1}/{max_retries}): {error_str}"
                        )

                        # 차단 이유 검사 및 처리
                        if (
                            "block_reason:" in error_str
                            or "prompt_feedback.block_reason:" in error_str
                        ):
                            try:
                                # 차단 이유 추출
                                if "block_reason:" in error_str:
                                    block_info = error_str.split("block_reason:")[
                                        1
                                    ].strip()
                                else:
                                    block_info = error_str.split(
                                        "prompt_feedback.block_reason:"
                                    )[1].strip()

                                block_reason = block_info.split()[
                                    0
                                ].strip()  # 첫 단어만 추출 (PROHIBITED_CONTENT 등)
                                print(f"📛 Detected block reason: {block_reason}")

                                # 즉시 차단 메시지 반환 (재시도 안 함)
                                return handle_message_block(
                                    BlockedPromptException(
                                        f"block_reason: {block_reason}"
                                    )
                                )
                            except Exception as extract_error:
                                print(
                                    f"⚠️ Error extracting block reason: {extract_error}"
                                )

                        # 차단 이유가 아닌 진짜 서버 오류인 경우에만 재시도
                        if retry == max_retries - 1:  # 마지막 시도였다면
                            print("❌ All retries failed")
                            return {
                                "answer": (
                                    "Sorry, the AI service is currently experiencing issues. "
                                    "Please try again later."
                                ),
                                "emotion": "Neutral",
                                "block_reason": "internal error"
                            }
                        import time

                        time.sleep(1)  # 1초 대기 후 재시도

        # 모델 최종 응답
        if convo.last:
            # error_catch = None
            response_text = convo.last.text
            # 유니코드 이스케이프 시퀀스 처리
            safe_print("before : ", response_text)
            response_text = process_mixed_unicode(response_text)
            response_text = response_text.replace("**", "").replace("\\*", "*")
            error_catch = internal_error_catch(response_text)
            if error_catch:
                return error_catch
            token = convo.last.usage_metadata.candidates_token_count
            print(token)
            if token >= 195:
                response_text = token_changer(model, response_text, history, token)
                print(
                    "🍇 token_changer activated! : ",
                    response_text,
                    "\n token count: ",
                    token,
                )
            safe_print("after : ", response_text)
        else:
            response_text = "No response from model."
        ########################################################################
        # 6) 감정 분석 로직
        ########################################################################
        # general_motion_list = [
        #     "Happiness",
        #     "Resignation",
        #     "Nervous",
        #     "Panic",
        #     "Ridiculous",
        #     "Sadness",
        #     "Anger",
        #     "Fear",
        #     "Surprise",
        #     "Disgust",
        #     "Love",
        #     "Excitement",
        #     "Gratitude",
        #     "Neutral",
        # ]

        general_motion_dict = {
            "positive emotion": [
                "Happiness",
                "Love",
                "Excitement",
                "Gratitude",
            ],
            "negative emotion": [
                "Resignation",
                "Nervous",
                "Panic",
                "Ridiculous",
                "Sadness",
                "Anger",
                "Fear",
                "Disgust",
            ],
            "neutral emotion": [
                "Neutral",
                "Surprise",
            ]
        }

        # mystery_motion_list = [
        #     "Explanation",
        #     "Ridiculous",
        #     "Nervous",
        #     "Panic",
        #     "Sorrow",
        #     "Sad",
        # ]

        mystery_motion_dict = {
            "neutral emotion": [
                "Explanation",
            ],
            "negative emotion": [
                "Ridiculous",
                "Nervous",
                "Panic",
                "Sorrow",
                "Sad",
            ]
        }

        def dict_together(input_dict):
            items = []
            for key, value_list in input_dict.items():
                items.append(f"{key}: {', '.join(value_list)}")
            return ", ".join(items)

        emotion_by_character_type = ""

        general_motion_str = dict_together(general_motion_dict)
        mystery_motion_str = dict_together(mystery_motion_dict)

        if character_type == "mystery":
            emotion_by_character_type = mystery_motion_str
        else:
            emotion_by_character_type = general_motion_str

        emotion_system_prompt = (
            f"You must choose just one of this emotions: ({emotion_by_character_type}). "
            "You should never say anything other than these words. "
            "Special characters should also never be used."
        )

        emotion_model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={"temperature": 0.1, "max_output_tokens": 20},
            system_instruction=emotion_system_prompt,
        )

        emotion_response = emotion_model.generate_content(contents=[response_text])

        response_emotion = emotion_response.text
        response_emotion = remove_special_characters(response_emotion)

        # llama3처럼 체크
        if response_emotion is None or not response_emotion.strip():
            response_emotion = (
                "Explanation" if character_type == "mystery" else "Neutral"
            )

        # 후보 안에 없으면 Neutral(또는 Explanation)
        valid_emotions = emotion_by_character_type.split(",")
        if response_emotion not in valid_emotions:
            if character_type == "mystery":
                response_emotion = "Explanation"
            else:
                response_emotion = "Neutral"

        print("emotion :", response_emotion)

    except Exception:
        import traceback

        print(f" ====== (google-generativeai) ERROR: {traceback.format_exc()} ======")
        response_text = "An error occurred."
        response_emotion = "Neutral"

    ########################################################################
    # 7) 최종 리턴
    ########################################################################
    return {"answer": response_text, "emotion": response_emotion, "block_reason": block_reason}
