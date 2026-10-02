"""Fixed reply templates for the two paths where the model must NOT improvise.

* refer   — Level D (personal fatwa / individual case): no ruling, refer to a
            qualified scholar (HANDOFF §5.4: a fixed, reviewed template).
* abstain — no evidence above the confidence threshold, or a hadith request with
            no authentic hadith in the approved sources (HANDOFF §5.7).

These texts must be reviewed by the team's content/sharia reviewer before the demo
(status tracked in docs/AGENT.md). Languages not listed are translated by the LLM
from the English text, with an instruction to keep the meaning exactly.
"""
from __future__ import annotations

REFER = {
    "ar": ("جزاك الله خيرًا على سؤالك. هذا السؤال يتعلق بحالتك الخاصة، والحكم فيه يحتاج إلى معرفة تفاصيل "
           "وضعك من عالِمٍ مؤهَّل، ولذلك لا نستطيع أن نعطيك حكمًا هنا. ننصحك بعرض سؤالك بتفاصيله على عالِمٍ "
           "أو جهة إفتاء موثوقة في بلدك، أو على مركز إسلامي قريب منك. ويسعدنا أن نجيبك عن أي سؤال عام عن الإسلام."),
    "en": ("Thank you for your question. It concerns your own personal situation, and a ruling on it needs a "
           "qualified scholar who can learn the details of your case, so we cannot give you a ruling here. "
           "Please put your question, with its details, to a trusted scholar or fatwa body in your country, or "
           "to an Islamic center near you. We are happy to answer any general question you have about Islam."),
    "ur": ("آپ کے سوال کا شکریہ۔ یہ سوال آپ کی ذاتی صورتحال سے متعلق ہے، اور اس کا حکم کسی مستند عالم ہی بتا سکتے "
           "ہیں جو آپ کے حالات کی تفصیل جان سکیں، اس لیے ہم یہاں کوئی حکم نہیں دے سکتے۔ براہِ کرم اپنا سوال تفصیل کے "
           "ساتھ اپنے ملک کے کسی معتبر عالم یا دارالافتاء، یا قریبی اسلامی مرکز کے سامنے رکھیں۔ اسلام کے بارے میں کسی "
           "بھی عمومی سوال کا جواب دینے میں ہمیں خوشی ہوگی۔"),
    "id": ("Terima kasih atas pertanyaan Anda. Pertanyaan ini menyangkut keadaan pribadi Anda, dan hukumnya perlu "
           "ditentukan oleh ulama yang berkompeten setelah mengetahui rincian keadaan Anda, sehingga kami tidak dapat "
           "memberikan fatwa di sini. Silakan sampaikan pertanyaan Anda beserta rinciannya kepada ulama atau lembaga "
           "fatwa terpercaya di negara Anda, atau ke pusat Islam terdekat. Kami senang menjawab pertanyaan umum "
           "tentang Islam."),
    "fr": ("Merci pour votre question. Elle concerne votre situation personnelle, et un avis à ce sujet demande un "
           "savant qualifié qui connaisse les détails de votre cas ; nous ne pouvons donc pas vous donner d'avis "
           "juridique ici. Nous vous invitons à poser votre question, avec ses détails, à un savant ou à une instance "
           "de fatwa reconnue dans votre pays, ou à un centre islamique proche de chez vous. Nous répondrons volontiers "
           "à toute question générale sur l'islam."),
}

# Level C (disputed / sensitive) with no evidence above the threshold: point to a specialist.
REFER_SPECIALIST = {
    "ar": ("سؤالك في موضوع يحتاج إلى بيانٍ علمي دقيق ومفصَّل، ولا نريد أن نجيب عنه إجابةً مختصرة قد تُفهَم "
           "على غير وجهها. ننصحك بعرضه على عالِمٍ متخصص أو جهة علمية موثوقة، ويسعدنا أن نساعدك في أي سؤال آخر عن الإسلام."),
    "en": ("Your question is about a topic that needs a careful, detailed scholarly explanation, and we do not want "
           "to give a short answer that could be misunderstood. We suggest putting it to a qualified specialist or a "
           "trusted scholarly body. We are happy to help with any other question you have about Islam."),
    "ur": ("آپ کا سوال ایسے موضوع سے متعلق ہے جس کے لیے محتاط اور تفصیلی علمی وضاحت درکار ہے، اور ہم ایسا مختصر جواب "
           "نہیں دینا چاہتے جو غلط سمجھا جائے۔ براہِ کرم اسے کسی مستند ماہر عالم یا معتبر علمی ادارے کے سامنے رکھیں۔ "
           "اسلام کے بارے میں کسی اور سوال میں مدد کر کے ہمیں خوشی ہوگی۔"),
    "id": ("Pertanyaan Anda menyangkut topik yang memerlukan penjelasan ilmiah yang cermat dan rinci, dan kami tidak "
           "ingin memberikan jawaban singkat yang bisa disalahpahami. Kami sarankan Anda menanyakannya kepada ulama "
           "yang ahli atau lembaga keilmuan terpercaya. Kami senang membantu pertanyaan lain tentang Islam."),
    "fr": ("Votre question porte sur un sujet qui demande une explication savante précise et détaillée, et nous ne "
           "voulons pas donner une réponse courte qui pourrait être mal comprise. Nous vous suggérons de la poser à un "
           "spécialiste qualifié ou à une instance savante reconnue. Nous serons heureux de vous aider pour toute "
           "autre question sur l'islam."),
}

ABSTAIN = {
    "ar": ("لم نجد في المصادر المعتمدة لدينا ما يكفي للإجابة عن هذا السؤال إجابةً موثَّقة، ولا نريد أن نقول شيئًا "
           "بلا مصدر. هل يمكنك توضيح سؤالك أكثر؟"),
    "en": ("We could not find enough in our approved sources to answer this question reliably, and we do not want "
           "to say anything without a source. Could you tell us a little more about what you would like to know?"),
    "ur": ("ہمیں اپنے معتبر ذرائع میں اس سوال کا مستند جواب دینے کے لیے کافی مواد نہیں ملا، اور ہم بغیر حوالے کے کچھ "
           "کہنا نہیں چاہتے۔ کیا آپ اپنا سوال کچھ مزید واضح کر سکتے ہیں؟"),
    "id": ("Kami tidak menemukan cukup bahan dalam sumber-sumber terpercaya kami untuk menjawab pertanyaan ini dengan "
           "akurat, dan kami tidak ingin mengatakan sesuatu tanpa sumber. Bisakah Anda menjelaskan pertanyaan Anda "
           "sedikit lebih rinci?"),
    "fr": ("Nous n'avons pas trouvé assez d'éléments dans nos sources approuvées pour répondre de façon fiable, et "
           "nous ne voulons rien affirmer sans source. Pourriez-vous préciser un peu votre question ?"),
}

ABSTAIN_HADITH = {
    "ar": ("لم نجد في المصادر المعتمدة لدينا حديثًا صحيحًا يطابق ما ذكرت، ولا يصح أن نَنسب إلى النبي ﷺ كلامًا "
           "دون مصدر موثَّق. إن كان لديك نص الحديث أو مصدره فأرسله لنا لنتحقق منه."),
    "en": ("We did not find an authentic hadith matching this in our approved sources, and it is not right to "
           "attribute words to the Prophet (peace be upon him) without a verified source. If you have the text "
           "of the hadith or where it comes from, send it to us and we will check it."),
    "ur": ("ہمیں اپنے معتبر ذرائع میں اس سے مطابقت رکھنے والی کوئی صحیح حدیث نہیں ملی، اور نبی ﷺ کی طرف کوئی بات "
           "مستند حوالے کے بغیر منسوب کرنا درست نہیں۔ اگر آپ کے پاس حدیث کا متن یا اس کا حوالہ ہے تو ہمیں بھیجیں تاکہ ہم "
           "اس کی تحقیق کر سکیں۔"),
    "id": ("Kami tidak menemukan hadis sahih yang sesuai dengan hal ini dalam sumber-sumber terpercaya kami, dan "
           "tidak benar menisbatkan perkataan kepada Nabi ﷺ tanpa sumber yang terverifikasi. Jika Anda memiliki teks "
           "atau sumber hadis tersebut, kirimkan kepada kami agar kami dapat memeriksanya."),
    "fr": ("Nous n'avons pas trouvé de hadith authentique correspondant dans nos sources approuvées, et il n'est pas "
           "permis d'attribuer des paroles au Prophète (paix sur lui) sans source vérifiée. Si vous avez le texte du "
           "hadith ou sa référence, envoyez-les-nous et nous les vérifierons."),
}


def pick(table: dict[str, str], lang: str) -> tuple[str, bool]:
    """(text, exact) — exact=False means the English text must be translated to `lang`."""
    if lang in table:
        return table[lang], True
    return table["en"], False
