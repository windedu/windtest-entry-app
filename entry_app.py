import streamlit as st
import requests
import os
import pandas as pd
from datetime import datetime

import re

# Load secrets (local .streamlit/secrets.toml or Streamlit Cloud Secrets)
try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
    STUDENT_DB_ID = st.secrets["STUDENT_DB_ID"]
    Q_DB_ID = st.secrets["Q_DB_ID"]
    R_DB_ID = st.secrets["R_DB_ID"]
    REPORT_DB_ID = st.secrets["REPORT_DB_ID"]
    ADMIN_USER_ID = st.secrets["ADMIN_USER_ID"]
except FileNotFoundError:
    st.error("Secrets not found! Please create .streamlit/secrets.toml or set them in Streamlit Cloud.")
    st.stop()
except KeyError as e:
    st.error(f"Missing secret: {e}")
    st.stop()

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

st.set_page_config(layout="wide", page_title="WindTest Data Entry")

def init_session_state():
    if "students" not in st.session_state:
        st.session_state.students = []
    if "tests" not in st.session_state:
        st.session_state.tests = []
    if "questions" not in st.session_state:
        st.session_state.questions = []
    if "selected_answers" not in st.session_state:
        st.session_state.selected_answers = {}

def natural_sort_key(s):
    """
    Sorts strings containing numbers naturally.
    Splits "1-1", "1-2", "1-10", "2" into ["1", "1"], ["1", "2"], ["1", "10"], ["2"].
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]


@st.cache_data(ttl=3600)
def fetch_students():
    url = f"https://api.notion.com/v1/databases/{STUDENT_DB_ID}/query"
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        try:
            res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results.extend(data["results"])
                has_more = data["has_more"]
                start_cursor = data["next_cursor"]
            else:
                st.error(f"Error fetching students: {res.text}")
                break
        except Exception as e:
            st.error(f"Exception fetching students: {e}")
            break
            
    # Parse into simplified list
    student_list = []
    for p in results:
        props = p["properties"]
        name_prop = props.get("이름", {}).get("title", [])
        if name_prop:
            name = name_prop[0]["text"]["content"]
            student_list.append({"id": p["id"], "name": name})
    
    return sorted(student_list, key=lambda x: x["name"])

@st.cache_data(ttl=3600)
def fetch_users():
    url = "https://api.notion.com/v1/users"
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        try:
            res = requests.get(url, headers=HEADERS, params={"start_cursor": start_cursor} if start_cursor else {}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results.extend(data["results"])
                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")
            else:
                break
        except Exception as e:
            break
            
    # Filter for people
    users = []
    for u in results:
        if u["type"] == "person":
             users.append({"id": u["id"], "name": u.get("name", "Unknown")})
             
    return users

@st.cache_data(ttl=600)
def fetch_tests():
    # Fetch unique test names from Questions DB properties
    url = f"https://api.notion.com/v1/databases/{Q_DB_ID}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            props = data["properties"]
            test_prop = props.get("시험명", {}).get("multi_select", {})
            options = test_prop.get("options", [])
            return sorted([opt["name"] for opt in options])
        else:
            st.error(f"Error fetching DB properties: {res.text}")
            return []
    except Exception as e:
        st.error(f"Exception fetching tests: {e}")
        return []

@st.cache_data(ttl=600)
def fetch_questions(test_name):
    url = f"https://api.notion.com/v1/databases/{Q_DB_ID}/query"
    filter_json = {
        "property": "시험명",
        "multi_select": {
            "contains": test_name
        }
    }
    
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100, "filter": filter_json}
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        try:
            res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results.extend(data["results"])
                has_more = data["has_more"]
                start_cursor = data["next_cursor"]
            else:
                st.error(f"Error fetching questions: {res.text}")
                break
        except Exception as e:
            st.error(f"Exception fetching questions: {e}")
            break
    
    # Process
    q_list = []
    for q in results:
        props = q["properties"]
        # Extract question number or text
        # '문제' is rich_text. '단원', '유형', '난이도' are select/multi_select
        
        # '이름' is Title (e.g. Test_Name_01)
        q_title = ""
        title_prop = props.get("이름", {}).get("title", [])
        if title_prop:
            q_title = title_prop[0]["text"]["content"]
            
        q_text = ""
        q_rich = props.get("문제", {}).get("rich_text", [])
        if q_rich:
            q_text = q_rich[0]["text"]["content"]
            
            
        # Extract Question Number from Title
        # Assume Title format: "TestName_{Number}"
        q_label = str(len(q_list) + 1) # Default to sequential
        if q_title:
            parts = q_title.split("_")
            if len(parts) > 1:
                q_label = parts[-1]
                # Strip leading zeros, but keep "0" if it's just "0"
                if len(q_label) > 1 and q_label.startswith("0"):
                     q_label = q_label.lstrip("0")

        q_list.append({
            "id": q["id"],
            "title": q_title, # Store Title
            "label": q_label, # Store Display Label
            "text": q_text,
            "unit": props.get("단원", {}).get("select", {}).get("name", ""),
            "type": [x["name"] for x in props.get("유형", {}).get("multi_select", [])],
            "difficulty": props.get("난이도", {}).get("select", {}).get("name", ""),
            "score": props.get("배점", {}).get("number", 0) # Get Score
        })
        

    
    # Sort q_list naturally by label
    # This handles "1-1" < "1-2" < "1-10" < "2" correctly if logic is Right.
    # Actually, "1-1" vs "2". split -> [1, "-", 1], [2]. 1 < 2. Correct.
    # "1" vs "1-1". [1], [1, "-", 1]. 1 == 1. len 1 < len 3. "1" comes first. Correct.
    q_list.sort(key=lambda x: natural_sort_key(x["label"]))
        
    return q_list

def fetch_existing_results(student_id, test_name):
    # Query Results DB for this student and test
    url = f"https://api.notion.com/v1/databases/{R_DB_ID}/query"
    filter_json = {
        "and": [
            {
                "property": "학생",
                "relation": {
                    "contains": student_id
                }
            },
            {
                "property": "시험명",
                "select": {
                    "equals": test_name
                }
            }
        ]
    }
    
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100, "filter": filter_json}
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        try:
            res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results.extend(data["results"])
                has_more = data["has_more"]
                start_cursor = data["next_cursor"]
            else:
                st.error(f"Error fetching results: {res.text}")
                break
        except Exception as e:
            st.error(f"Exception fetching results: {e}")
            break
            
    # Map question_id -> result_outcome
    existing_map = {}
    for r in results:
        props = r["properties"]
        # '문항' is relation
        q_rels = props.get("문항", {}).get("relation", [])
        if q_rels:
            q_id = q_rels[0]["id"]
            outcome = props.get("정오", {}).get("select", {}).get("name", "")
            existing_map[q_id] = outcome
            
    return existing_map

def create_report_entry(student_id, student_name, test_name, score, teacher_id, exam_date_str, time_taken=0):
    # 1. Check if entry exists
    url = f"https://api.notion.com/v1/databases/{REPORT_DB_ID}/query"
    payload = {
        "filter": {
            "and": [
                {
                    "property": "학생",
                    "relation": {
                        "contains": student_id
                    }
                },
                {
                    "property": "시험명",
                    "select": {
                        "equals": test_name
                    }
                }
            ]
        }
    }
    
    existing_page_id = None
    try:
        res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results:
                existing_page_id = results[0]["id"]
    except Exception as e:
        print(f"Error querying report DB: {e}")

    # Properties to set
    props = {
        "이름": {"title": [{"text": {"content": f"{student_name} - {test_name}"}}]},
        "학생": {"relation": [{"id": student_id}]},
        "시험명": {"select": {"name": test_name}},
        "점수": {"number": score},
        "보고서 상태": {"select": {"name": "1. 입력 완료"}},
        "응시일": {"date": {"start": exam_date_str}},
        "담당 선생님": {"people": [{"id": teacher_id}]} if teacher_id else {"people": []}
    }
    
    if time_taken > 0:
        props["소요시간"] = {"number": time_taken}
    
    if existing_page_id:
        # Update
        url_update = f"https://api.notion.com/v1/pages/{existing_page_id}"
        try:
             requests.patch(url_update, headers=HEADERS, json={"properties": props}, timeout=10)
             print(f"Updated Report Entry: {existing_page_id}")
             # Add comment? Only if defining notification policy. 
             # Policy: "항목이 생성되었다면... 알람". 
             # If updated, strictly speaking it's not created. But let's notify anyway to be safe, or logic: 
             # "입력 완료" status trigger. 
             send_notification(existing_page_id, ADMIN_USER_ID, "시험 점수 입력이 완료되었습니다. 리포트 생성을 부탁드립니다.")
        except Exception as e:
             print(f"Error updating report: {e}")
    else:
        # Create
        url_create = "https://api.notion.com/v1/pages"
        payload_create = {
            "parent": {"database_id": REPORT_DB_ID},
            "properties": props
        }
        try:
            res = requests.post(url_create, headers=HEADERS, json=payload_create, timeout=10)
            if res.status_code == 200:
                new_page_id = res.json()["id"]
                print(f"Created Report Entry: {new_page_id}")
                send_notification(new_page_id, ADMIN_USER_ID, "시험 점수 입력이 완료되었습니다. 리포트 생성을 부탁드립니다.")
            else:
                print(f"Error creating report: {res.text}")
        except Exception as e:
             print(f"Error creating report: {e}")

def send_notification(page_id, target_user_id, message):
    url = "https://api.notion.com/v1/comments"
    payload = {
        "parent": {"page_id": page_id},
        "rich_text": [
            {
                "text": {"content": message + " "}
            },
            {
                "mention": {"user": {"id": target_user_id}}
            }
        ]
    }
    try:
        requests.post(url, headers=HEADERS, json=payload, timeout=5)
    except:
        pass

def submit_results(final_outcomes, questions):
    """
    final_outcomes: dict {q_id: "정답" or "오답"}
    questions: list of question dicts (to get text for title)
    """
    if "current_student" not in st.session_state or "current_test" not in st.session_state:
        return

    student_id = st.session_state.current_student["id"]
    test_name = st.session_state.current_test
    
    # Re-fetch existing to know ID if update needed
    existing_map = fetch_existing_results_full(student_id, test_name) # Need full object to get Page ID
    
    success_count = 0
    fail_count = 0
    
    progress_bar = st.progress(0)
    
    # Create lookup for question title and score
    q_meta_map = {q["id"]: q for q in questions}
    
    # Iterate over final_outcomes
    total = len(final_outcomes)
    total_score = 0
    
    for i, (q_id, outcome) in enumerate(final_outcomes.items()):
        
        # Calculate Score
        if outcome == "정답":
            total_score += q_meta_map.get(q_id, {}).get("score", 0)
        
        # Check if exists
        existing_page_id = existing_map.get(q_id)
        
        if existing_page_id:
            # Update
            url = f"https://api.notion.com/v1/pages/{existing_page_id}"
            payload = {
                "properties": {
                    "정오": {"select": {"name": outcome}},
                    "응시일": {"date": {"start": st.session_state.get("exam_date", datetime.now()).isoformat()}}
                }
            }
            try:
                res = requests.patch(url, headers=HEADERS, json=payload, timeout=10)
                if res.status_code == 200:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"Error updating: {res.text}")
            except:
                fail_count += 1
        else:
            # Create
            url = "https://api.notion.com/v1/pages"
            
            # Construct Title: {s_name}-{t_name}-{q_num}
            s_name = st.session_state.current_student["name"]
            
            q_title = q_meta_map.get(q_id, {}).get("title", "")
            # Assume format "..._Num" e.g. "Test_Name_01"
            try:
                q_num_part = q_title.split("_")[-1]
            except:
                q_num_part = q_id # Fallback
                
            res_title = f"{s_name}-{test_name}-{q_num_part}"
            
            payload = {
                "parent": {"database_id": R_DB_ID},
                "properties": {
                    "이름": {"title": [{"text": {"content": res_title}}]},
                    "학생": {"relation": [{"id": student_id}]},
                    "문항": {"relation": [{"id": q_id}]},
                    "시험명": {"select": {"name": test_name}},
                    "정오": {"select": {"name": outcome}},
                    "응시일": {"date": {"start": st.session_state.get("exam_date", datetime.now()).isoformat()}}
                }
            }
            try:
                res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
                if res.status_code == 200:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"Error creating: {res.text}")
            except:
                fail_count += 1
        
        progress_bar.progress((i + 1) / total)
        
    st.success(f"Saved! Success: {success_count}, Failed: {fail_count}")
    
    # Create/Update Report Entry
    if "selected_teacher" in st.session_state and st.session_state.selected_teacher:
         teacher_id = st.session_state.selected_teacher["id"]
    else:
         teacher_id = None 
         
    exam_date_str = st.session_state.get("exam_date", datetime.now()).isoformat()
    
    # Get Time if applicable
    time_taken = st.session_state.get("time_taken", 0)
    
    if success_count > 0:
         create_report_entry(student_id, st.session_state.current_student["name"], test_name, total_score, teacher_id, exam_date_str, time_taken)
         st.info("Updated Report Management DB and notified administrator.")

def fetch_existing_results_full(student_id, test_name):
    # Same as fetch_existing_results but returns Map[q_id] -> page_id
    url = f"https://api.notion.com/v1/databases/{R_DB_ID}/query"
    filter_json = {
        "and": [
            {
                "property": "학생",
                "relation": {
                    "contains": student_id
                }
            },
            {
                "property": "시험명",
                "select": {
                    "equals": test_name
                }
            }
        ]
    }
    
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100, "filter": filter_json}
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        try:
            res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results.extend(data["results"])
                has_more = data["has_more"]
                start_cursor = data["next_cursor"]
            else:
                break
        except:
            break
            
    # Map question_id -> page_id
    existing_map = {}
    for r in results:
        props = r["properties"]
        q_rels = props.get("문항", {}).get("relation", [])
        if q_rels:
            q_id = q_rels[0]["id"]
            existing_map[q_id] = r["id"]
            
    return existing_map

def parse_input_labels(text):
    """Parse comma/space/newline separated labels from text."""
    labels = []
    if not text: return labels
    
    # Replace common separators with space
    text = text.replace(",", " ").replace(";", " ").replace("\n", " ")
    parts = text.split()
    for p in parts:
        val = p.strip()
        # Strip leading zeros for matching logic (e.g. user types "03", match with "3")
        if len(val) > 1 and val.startswith("0"):
            val = val.lstrip("0")
        labels.append(val)
    return labels

def main():
    st.title("WindTest Result Entry")
    
    # Keyboard valid shortcut for saving (Cmd+Enter / Ctrl+Enter)
    # This script finds the button with text "Save Results" or specific hierarchy and clicks it.
    # Since we can't easily target by ID, we might need a workaround or assume the button exists.
    # Better: Add a dummy form or global listener.
    st.markdown("""
    <script>
    document.addEventListener('keydown', function(e) {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            // Target the "Save Results" button. 
            // Streamlit buttons don't have stable IDs. We can look for inner text.
            const buttons = Array.from(document.getElementsByTagName('button'));
            const saveBtn = buttons.find(b => b.innerText.includes("Save Results"));
            if (saveBtn) {
                saveBtn.click();
                e.preventDefault();
            }
        }
    });
    </script>
    """, unsafe_allow_html=True)

    init_session_state()
    
    # Sidebar for selection
    with st.sidebar:
        st.header("Selection")
        
        # 1. Select Student
        students = fetch_students()
        student_names = [s["name"] for s in students]
        
        # Determine index for default
        st_idx = 0
        if "current_student" in st.session_state:
             try:
                 st_idx = student_names.index(st.session_state.current_student["name"]) + 1
             except: pass
             
        selected_student_name = st.selectbox("Select Student", [""] + student_names, index=st_idx)
        
        # 2. Select Test
        tests = fetch_tests()
        t_idx = 0
        if "current_test" in st.session_state:
            try:
                t_idx = tests.index(st.session_state.current_test) + 1
            except: pass
            
        selected_test = st.selectbox("Select Test", [""] + tests, index=t_idx)
        
        if st.button("Load Questions"):
            if not selected_student_name or not selected_test:
                st.warning("Please select both student and test.")
            else:
                st.session_state.current_student = next(s for s in students if s["name"] == selected_student_name)
                st.session_state.current_test = selected_test
                # Clear previous answers if loading new
                st.session_state.selected_answers = {} 
                st.experimental_rerun()

        # 3. Select Date
        exam_date = st.date_input("Exam Date", value=datetime.now())
        st.session_state.exam_date = exam_date
        
        # 4. Select Teacher
        # Defined Teacher List
        TEACHERS = [
            {"name": "김지현", "email": "agnesejh@gmail.com"},
            {"name": "김소연", "email": "a88755505@gmail.com"},
            {"name": "서승용", "email": "primenumber199@gmail.com"},
            {"name": "이승규", "email": "ggobssal@postech.ac.kr"}
        ]
        
        users = fetch_users()
        # Create lookup maps
        user_email_map = {u["email"]: u for u in users if u.get("email")}
        user_name_map = {u["name"]: u for u in users}
        
        teacher_names = [t["name"] for t in TEACHERS]
        selected_teacher_name = st.selectbox("Select Teacher", [""] + teacher_names)
        
        st.session_state.selected_teacher = None
        if selected_teacher_name:
            selected_config = next(t for t in TEACHERS if t["name"] == selected_teacher_name)
            
            # Try matching by Email then Name
            matched_user = user_email_map.get(selected_config["email"])
            if not matched_user:
                # Try Name Match
                # 1. Exact Name
                matched_user = user_name_map.get(selected_config["name"]) # e.g. 김지현
                
                if not matched_user:
                    # 2. Try English Order / spaced check (e.g. Notion has "지현 김")
                    # Normalized Notion names: remove spaces
                    # But user_name_map keys are raw Notion names.
                    target_name_clean = selected_config["name"].replace(" ", "") # 김지현
                    
                    for u_name, u_obj in user_name_map.items():
                        # u_name e.g. "지현 김"
                        u_clean = u_name.replace(" ", "") # 지현김
                        
                        # Direct clean match
                        if u_clean == target_name_clean:
                            matched_user = u_obj
                            break
                        
                        # Reverse check (Korean Name "LastFirst" vs Notion "First Last")
                        # u_name "지현 김" -> split ["지현", "김"] -> reverse ["김", "지현"] -> join "김지현"
                        parts = u_name.split(" ")
                        if len(parts) == 2:
                            reversed_clean = "".join(list(reversed(parts))) # 김지현
                            if reversed_clean == target_name_clean:
                                matched_user = u_obj
                                break
            
            if matched_user:
                st.session_state.selected_teacher = matched_user
            else:
                st.warning(f"Notion User not found for {selected_teacher_name}. Report will be saved without teacher tag.")
                # We can store the name temporarily in session state if needed, but DB requires ID for Person prop.
                # So we leave selected_teacher as None.

        # 5. Input Mode
        st.markdown("---")
        input_mode = st.radio(
            "Input Mode", 
            ["Individual Entry", "Input Correct Numbers", "Input Incorrect Numbers"],
            key="input_mode"
        )

    # Inject Custom CSS
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] {
                min-width: 500px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Main Area
    if "current_student" in st.session_state and "current_test" in st.session_state:
        st.subheader(f"Entering scores for: {st.session_state.current_student['name']} - {st.session_state.current_test}")
        
        # --- Time Input Logic ---
        test_name = st.session_state.current_test
        if test_name.startswith("기초") or test_name.startswith("심화"):
            st.session_state.time_taken = st.number_input("소요시간 (분)", min_value=0, step=1, value=0)
        else:
            st.session_state.time_taken = 0
        # ------------------------
        
        # Fetch Questions and Existing Results
        questions = fetch_questions(st.session_state.current_test)
        existing_results = fetch_existing_results(st.session_state.current_student["id"], st.session_state.current_test)
        
        if not questions:
            st.warning("No questions found for this test.")
        else:
            final_outcomes_to_save = {}
            
            with st.form("score_entry_form"):
                
                mode = st.session_state.get("input_mode", "Individual Entry")
                
                if mode == "Individual Entry":
                    for i, q in enumerate(questions):
                        # Display Question Label instead of Index
                        st.markdown(f"**{q['label']}번** ({q['unit']} / {q['type']} / {q['difficulty']})")
                        
                        # Determine default
                        default_outcome = existing_results.get(q["id"], "정답") 
                        
                        # Grading Logic: Only O/X
                        opts = ["정답", "오답"]
                        idx = 0
                        if default_outcome in opts:
                            idx = opts.index(default_outcome)
                        
                        selection = st.radio(
                            f"Outcome for {i+1}", 
                            opts, 
                            index=idx, 
                            key=f"q_{q['id']}", 
                            horizontal=True,
                            label_visibility="collapsed"
                        )
                        st.markdown("---")
                        
                        final_outcomes_to_save[q["id"]] = selection
                        
                else: # Batch Input Modes
                    st.info(f"Mode: {mode}. Please enter the **question numbers** (e.g. 1-1, 03) separated by space, comma, or newline.")
                    
                    raw_input = st.text_area("Question Numbers", height=150)
                    
                    # Logic to parse and preview
                    input_labels = parse_input_labels(raw_input)
                    
                    st.markdown("### Preview")
                    
                    preview_data = []
                    
                    for i, q in enumerate(questions):
                        q_label = q["label"]
                        
                        if mode == "Input Correct Numbers":
                            # If label in input -> Correct, else Incorrect
                            if q_label in input_labels:
                                outcome = "정답"
                            else:
                                outcome = "오답"
                        else: # Input Incorrect Numbers
                            if q_label in input_labels:
                                outcome = "오답"
                            else:
                                outcome = "정답"
                                
                        final_outcomes_to_save[q["id"]] = outcome
                        preview_data.append({"No": q_label, "Result": outcome, "ID": q["id"]})
                        
                    # Show a dataframe or simple list for verification
                    st.dataframe(pd.DataFrame(preview_data)[["No", "Result"]], hide_index=True)
                
                
                if st.form_submit_button("Save Results"):
                    # Validate Time if required
                    if (test_name.startswith("기초") or test_name.startswith("심화")) and st.session_state.time_taken <= 0:
                        st.error("소요시간을 입력해주세요 (0분 초과).")
                    else:
                        submit_results(final_outcomes_to_save, questions)

if __name__ == "__main__":
    main()
