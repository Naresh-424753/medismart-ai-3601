"""Spoken symptom words in Indian languages -> the English symptom names used by the rule-based checker.

Lets a villager speak (browser speech recognition, no server key needed) and still get a symptom check.
Substring matching on the recognised text. IMPORTANT: written for this project, NOT reviewed by native speakers - have a
native speaker per language review/extend `TERMS` before real-world use. Unknown words simply find nothing.
"""
from __future__ import annotations

TERMS: dict[str, dict[str, list[str]]] = {
    "hi": {"fever": ["बुखार", "बुखार", "ज्वर", "bukhar"], "cough": ["खांसी", "खाँसी", "khansi"], "headache": ["सिर दर्द", "सिरदर्द", "सर दर्द", "sar dard"],
           "chest pain": ["सीने में दर्द", "छाती में दर्द", "सीने का दर्द", "seene mein dard"], "shortness of breath": ["सांस फूल", "साँस फूल", "सांस लेने में तकलीफ", "सांस नहीं"],
           "vomiting": ["उल्टी", "ulti"], "diarrhea": ["दस्त", "पतला पखाना", "dast"], "stomach pain": ["पेट दर्द", "पेट में दर्द", "pet dard"], "body ache": ["बदन दर्द", "शरीर में दर्द", "बदन टूट"],
           "dizziness": ["चक्कर"], "sore throat": ["गले में दर्द", "गला खराब", "गले में खराश"], "runny nose": ["नाक बह", "बहती नाक"], "weakness": ["कमजोरी", "कमज़ोरी"], "rash": ["दाने", "चकत्ते"],
           "joint pain": ["जोड़ों में दर्द", "घुटने में दर्द"], "nausea": ["जी मिचल", "मितली"], "itching": ["खुजली"], "chills": ["ठंड लगना", "कंपकंपी"]},
    "bn": {"fever": ["জ্বর"], "cough": ["কাশি"], "headache": ["মাথা ব্যথা", "মাথাব্যথা"], "chest pain": ["বুকে ব্যথা", "বুক ব্যথা"], "shortness of breath": ["শ্বাসকষ্ট", "শ্বাস নিতে কষ্ট"],
           "vomiting": ["বমি"], "diarrhea": ["পাতলা পায়খানা", "ডায়রিয়া"], "stomach pain": ["পেট ব্যথা", "পেটে ব্যথা"], "body ache": ["গা ব্যথা", "শরীর ব্যথা"], "dizziness": ["মাথা ঘোরা"],
           "sore throat": ["গলা ব্যথা"], "runny nose": ["নাক দিয়ে পানি", "সর্দি"], "weakness": ["দুর্বলতা", "দুর্বল"], "rash": ["ফুসকুড়ি"], "joint pain": ["জোড়ায় ব্যথা", "হাঁটুতে ব্যথা"], "itching": ["চুলকানি"]},
    "ta": {"fever": ["காய்ச்சல்"], "cough": ["இருமல்"], "headache": ["தலைவலி"], "chest pain": ["நெஞ்சு வலி", "மார்பு வலி"], "shortness of breath": ["மூச்சுத் திணறல்", "மூச்சு விட சிரமம்"],
           "vomiting": ["வாந்தி"], "diarrhea": ["வயிற்றுப்போக்கு"], "stomach pain": ["வயிற்று வலி", "வயிறு வலி"], "body ache": ["உடல் வலி"], "dizziness": ["தலைசுற்றல்"],
           "sore throat": ["தொண்டை வலி"], "runny nose": ["மூக்கு ஒழுகல்"], "weakness": ["பலவீனம்", "சோர்வு"], "rash": ["தடிப்பு"], "joint pain": ["மூட்டு வலி"], "itching": ["அரிப்பு"]},
    "te": {"fever": ["జ్వరం"], "cough": ["దగ్గు"], "headache": ["తలనొప్పి"], "chest pain": ["ఛాతీ నొప్పి", "గుండె నొప్పి"], "shortness of breath": ["ఊపిరి ఆడటం లేదు", "శ్వాస తీసుకోవడం కష్టం"],
           "vomiting": ["వాంతులు", "వాంతి"], "diarrhea": ["విరేచనాలు"], "stomach pain": ["కడుపు నొప్పి"], "body ache": ["ఒళ్ళు నొప్పులు", "ఒంటి నొప్పులు"], "dizziness": ["తల తిరుగుతోంది", "కళ్ళు తిరగడం"],
           "sore throat": ["గొంతు నొప్పి"], "runny nose": ["ముక్కు కారడం"], "weakness": ["నీరసం", "బలహీనత"], "rash": ["దద్దుర్లు"], "joint pain": ["కీళ్ల నొప్పులు"], "itching": ["దురద"]},
    "mr": {"fever": ["ताप"], "cough": ["खोकला"], "headache": ["डोकेदुखी", "डोके दुखत"], "chest pain": ["छातीत दुखत", "छातीत दुखणे"], "shortness of breath": ["दम लागतो", "श्वास घेण्यास त्रास"],
           "vomiting": ["उलटी"], "diarrhea": ["जुलाब"], "stomach pain": ["पोटदुखी", "पोट दुखत"], "body ache": ["अंगदुखी", "अंग दुखत"], "dizziness": ["चक्कर"],
           "sore throat": ["घसा दुखत", "घशात खवखव"], "runny nose": ["नाक वाहते"], "weakness": ["अशक्तपणा", "थकवा"], "rash": ["पुरळ"], "joint pain": ["सांधेदुखी"], "itching": ["खाज"]},
    "gu": {"fever": ["તાવ"], "cough": ["ઉધરસ"], "headache": ["માથાનો દુખાવો", "માથું દુખે"], "chest pain": ["છાતીમાં દુખાવો"], "shortness of breath": ["શ્વાસ ચડે", "શ્વાસ લેવામાં તકલીફ"],
           "vomiting": ["ઉલટી"], "diarrhea": ["ઝાડા"], "stomach pain": ["પેટમાં દુખાવો", "પેટ દુખે"], "body ache": ["શરીરમાં દુખાવો", "અંગ દુખે"], "dizziness": ["ચક્કર"],
           "sore throat": ["ગળામાં દુખાવો"], "runny nose": ["નાક વહે"], "weakness": ["નબળાઈ", "અશક્તિ"], "rash": ["ચકામા"], "joint pain": ["સાંધાનો દુખાવો"], "itching": ["ખંજવાળ"]},
    "kn": {"fever": ["ಜ್ವರ"], "cough": ["ಕೆಮ್ಮು"], "headache": ["ತಲೆನೋವು"], "chest pain": ["ಎದೆ ನೋವು"], "shortness of breath": ["ಉಸಿರಾಟದ ತೊಂದರೆ", "ಉಸಿರು ಕಟ್ಟು"],
           "vomiting": ["ವಾಂತಿ"], "diarrhea": ["ಭೇದಿ"], "stomach pain": ["ಹೊಟ್ಟೆ ನೋವು"], "body ache": ["ಮೈ ಕೈ ನೋವು", "ಮೈ ನೋವು"], "dizziness": ["ತಲೆ ಸುತ್ತು"],
           "sore throat": ["ಗಂಟಲು ನೋವು"], "runny nose": ["ಮೂಗು ಸೋರು"], "weakness": ["ಆಯಾಸ", "ಬಲಹೀನತೆ"], "rash": ["ಗುಳ್ಳೆ", "ದದ್ದು"], "joint pain": ["ಕೀಲು ನೋವು"], "itching": ["ತುರಿಕೆ"]},
    "ml": {"fever": ["പനി"], "cough": ["ചുമ"], "headache": ["തലവേദന"], "chest pain": ["നെഞ്ചുവേദന", "നെഞ്ച് വേദന"], "shortness of breath": ["ശ്വാസംമുട്ടൽ", "ശ്വാസം മുട്ട്"],
           "vomiting": ["ഛർദ്ദി"], "diarrhea": ["വയറിളക്കം"], "stomach pain": ["വയറുവേദന", "വയറ് വേദന"], "body ache": ["ശരീര വേദന", "ദേഹവേദന"], "dizziness": ["തലകറക്കം"],
           "sore throat": ["തൊണ്ടവേദന"], "runny nose": ["മൂക്കൊലിപ്പ്"], "weakness": ["ക്ഷീണം", "തളർച്ച"], "rash": ["തടിപ്പ്"], "joint pain": ["സന്ധിവേദന"], "itching": ["ചൊറിച്ചിൽ"]},
    "pa": {"fever": ["ਬੁਖਾਰ"], "cough": ["ਖੰਘ"], "headache": ["ਸਿਰ ਦਰਦ", "ਸਿਰਦਰਦ"], "chest pain": ["ਛਾਤੀ ਵਿੱਚ ਦਰਦ", "ਸੀਨੇ ਵਿੱਚ ਦਰਦ"], "shortness of breath": ["ਸਾਹ ਚੜ੍ਹਦਾ", "ਸਾਹ ਲੈਣ ਵਿੱਚ ਤਕਲੀਫ"],
           "vomiting": ["ਉਲਟੀ"], "diarrhea": ["ਦਸਤ"], "stomach pain": ["ਪੇਟ ਦਰਦ", "ਪੇਟ ਵਿੱਚ ਦਰਦ"], "body ache": ["ਸਰੀਰ ਦਰਦ", "ਬਦਨ ਦਰਦ"], "dizziness": ["ਚੱਕਰ"],
           "sore throat": ["ਗਲੇ ਵਿੱਚ ਦਰਦ"], "runny nose": ["ਨੱਕ ਵਗਦਾ"], "weakness": ["ਕਮਜ਼ੋਰੀ"], "rash": ["ਧੱਫੜ"], "joint pain": ["ਜੋੜਾਂ ਦਾ ਦਰਦ"], "itching": ["ਖੁਜਲੀ"]},
}


def to_english(text: str, lang: str) -> list[str]:
    """English symptom names found in the spoken/typed text (order of the table, no duplicates)."""
    low = (text or "").lower()
    out: list[str] = []
    for lc in dict.fromkeys([lang, "hi"]) if lang in TERMS else ["hi"]:
        for eng, words in TERMS.get(lc, {}).items():
            if eng not in out and any(w.lower() in low for w in words):
                out.append(eng)
    return out
