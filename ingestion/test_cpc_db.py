import os
import torch
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Dict, Any


class CPCMultiPassFusionEngine:
    def __init__(self, chroma_db_path: str, collection_name: str = "cpc_patent_classification"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Engine Core] Mounting multi-pass fusion resources on device: {self.device.upper()}")

        # 1. Connect directly to your persistent storage folder path
        self.chroma_client = chromadb.PersistentClient(path=chroma_db_path)
        self.collection = self.chroma_client.get_collection(name=collection_name)

        # 2. Load the Bi-Encoder Model for standalone query coordinate calculations
        self.bi_encoder = SentenceTransformer("datalyes/patembed-large", device=self.device)
        self.bi_encoder.max_seq_length = 512
        self.bi_encoder.tokenizer.model_max_length = 512
        if self.device == "cuda":
            self.bi_encoder.half()

        # 3. Initialize the Cross-Encoder Re-ranker Matrix
        print("[Engine Core] Initializing Re-ranker ('BAAI/bge-reranker-large')...")
        self.reranker = CrossEncoder("BAAI/bge-reranker-large", device=self.device)

    def recommend_multi_pass(self, full_abstract: str, structural: str, procedural: str, functional: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Executes three specialized independent vector query sweeps

        and fuses the candidate spaces natively via Cross-Encoder re-ranking.
        """
        # Unique candidate lookup to prevent duplicate records across query sweeps
        unique_candidates = {}

        # Define our three specialized vector target queries
        queries = {
            "STRUCTURAL": f"Structural hardware components elements devices apparatus: {structural}",
            "PROCEDURAL": f"Procedural steps methods operations protocol algorithms: {procedural}",
            "FUNCTIONAL": f"Functional objective purpose utility use-case capability: {functional}",
        }

        # Execute individual specialized sweeps
        for query_type, query_text in queries.items():
            if not query_text.strip():
                continue

            with torch.no_grad():
                query_vector = self.bi_encoder.encode(query_text, convert_to_numpy=True).tolist()

            # Extract a wide, targeted pool from each distinct technological facet
            retrieval_pool_size = 40
            raw_results = self.collection.query(query_embeddings=[query_vector], n_results=retrieval_pool_size)

            if raw_results and raw_results["documents"] and len(raw_results["documents"]) > 0:
                # FIXED: Strip the outer query index matrix dimension row
                docs = raw_results["documents"][0]
                metadatas = raw_results["metadatas"][0]

                # Consolidate and deduplicate into our master tracking layout cleanly
                for idx, doc in enumerate(docs):
                    cpc_code = metadatas[idx]["cpc_code"]
                    title = metadatas[idx]["title"]

                    if cpc_code not in unique_candidates:
                        unique_candidates[cpc_code] = {"doc": doc, "title": title}

        print(f"[Search Status] Multi-pass fusion completed. {len(unique_candidates)} unique candidates pooled.")

        if not unique_candidates:
            return []

        # --- Stage 2: Direct Context Cross-Encoding ---
        # Re-rank the deduplicated pool against the FULL abstract to re-establish the connective context
        cpc_codes = list(unique_candidates.keys())
        rerank_pairs = [[full_abstract, unique_candidates[code]["doc"]] for code in cpc_codes]

        rerank_scores = self.reranker.predict(rerank_pairs)

        final_ranking = []
        for idx, code in enumerate(cpc_codes):
            final_ranking.append({"cpc_code": code, "title": unique_candidates[code]["title"], "confidence_score": float(rerank_scores[idx])})

        # Sort candidates descending by cross-encoder score
        final_ranking.sort(key=lambda x: x["confidence_score"], reverse=True)
        return final_ranking[:top_k]


# =====================================================================
# Main Control Execution Entrypoint
# =====================================================================
if __name__ == "__main__":
    # Determine directory location dynamically
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

    # Handle both positions: whether script sits at root or inside /ingestion folder
    if os.path.basename(SCRIPT_DIR) == "ingestion":
        ROOT_DIR = os.path.dirname(SCRIPT_DIR)
    else:
        ROOT_DIR = SCRIPT_DIR

    # Lock paths exactly to the shared DB data repository location on your hard drive
    CHROMADB_STORAGE_PATH = os.path.join(ROOT_DIR, "data", "chroma_db", "full_cpc_db")

    engine = CPCMultiPassFusionEngine(chroma_db_path=CHROMADB_STORAGE_PATH)

    # 1. Full Abstract Context
    abstract = (
        "A method for indicating a state of a battery of a vehicle when the vehicle has suffered an accident. "
        "Acoustic signals, which include coded items of information about at least one operating parameter "
        "of the battery, are sent by a loudspeaker of the vehicle. The acoustic signals are received by a "
        "microphone of a terminal and the coded items of information are decoded and output by the terminal."
    )

    # test_disclosure = (
    #     "Systems and methods are provided for establishing a backhaul connection in a wireless network. "
    #     "Methods include determining that broadband internet connectivity for a plurality of user equipment (UEs) is abnormal. "
    #     "The methods further include determining that one or more UEs of the plurality of UEs have a backhaul cellular capability "
    #     "and transmitting a backhaul request token to a selected UE among the one or more UEs that have the backhaul cellular capability. "
    #     "In addition, the methods include receiving backhaul acceptance from the selected UE among the one or more UEs that has the "
    #     "backhaul cellular capability and establishing backhaul connectivity for the plurality of UEs via the selected UE that has the "
    #     "backhaul cellular capability."
    # )

    # test_disclosure = (
    #     "A method for indicating a state of a battery of a vehicle when the vehicle has suffered an accident, in which acoustic signals, "
    #     "which include coded items of information about at least one operating parameter of the battery, are sent by a loudspeaker of the vehicle."
    #     "The acoustic signals are received by a microphone of a terminal and the coded items of information are decoded and output by the terminal."
    # )

    test_disclosure = (
        "    [0006] Against this background, one object was to suitably indicate dangers that could arise from a battery-operated vehicle after an accident."
        "[0007] The method according to the invention is provided for indicating a state of a battery of a vehicle after the vehicle has suffered an accident. In the method, acoustic signals are sent or emitted by a loudspeaker of the vehicle, which include coded items of information about at least one operating parameter of the battery of the vehicle. These acoustic signals are received by a microphone of an external, vehicle-independent terminal. Furthermore, the items of coded information within the acoustic signals are decoded by the terminal device, usually a computing unit of the terminal device, and output by an acoustic and/or optical display device of the terminal device to or for a user of the terminal device in a visually and/or acoustically comprehensible manner, whereby the user is informed about the state of the battery after the accident of the vehicle."
        "[0008] The method provides that the vehicle, for example a control unit of the vehicle, has a modulator for acoustic signals, which is designed to modulate the coded items of information about the state of the battery as acoustic signals and/or to modulate them onto further acoustic signals wherein the coded items of information are modulated accordingly and, for example, are modulated as primary acoustic signals onto further, secondary acoustic signals. It is thus possible for the loudspeaker to send two types of acoustic signals. The acoustic signals sent overall include the modulated and coded items of information as primary acoustic signals and further secondary acoustic signals, which are usually audible to a human, and which usually audibly indicate a possible danger arising from the battery as alarm signals."
        "[0009] However, it is also possible that the primary acoustic signals having the coded items of information are also audible by a human, wherein these primary acoustic signals as carriers of the coded items of information can be at least partially or completely digitized."
        "[0010] In one embodiment, the coded items of information about the operating state of the battery are sent via acoustic signals at a frequency that is greater than a frequency for acoustic signals that is audible to a human. The audible, usually secondary acoustic signals comprise at least alarm tones or warning tones. However, it is also possible for the loudspeaker to use acoustically perceptible signals which explicitly and in text form indicate the existing danger that can arise from the battery. The user can thus be informed that a danger has arisen from a battery of the vehicle, and/or that it has reached a critical temperature."
        "[0011] Regardless of whether signals that explicitly indicate the danger from the battery are now acoustically perceptible and/or coded and/or acoustically imperceptible because they are sent on the frequency that is above the perceptible frequency, they comprise, for example, items of information about a temperature and/or a state of charge as the at least one operating parameter of the battery."
        "[0012] Furthermore, it is possible for a volume and/or a frequency of the perceptible acoustic signals to be varied as a function of the at least one operating state of the battery. It is possible to set the volume and/or the frequency higher, the higher or more critical the danger is. Regardless of this, the signals which comprise the items information about the at least one operating parameter and are coded and optionally modulated can be provided as ultrasonic signals or hypersonic signals."
        "[0013] According to one embodiment, the acoustic signals of the loudspeaker therefore have an imperceptible part and a perceptible part."
        "[0014] It is also provided that the method is carried out for a vehicle that has a battery, for example, a traction battery and/or high-voltage battery, in which electrical energy for driving or moving the vehicle is stored."
        "[0015] The method can in principle be carried out when the vehicle has suffered the accident, regardless of how serious the accident is. The method is carried out in particular if the vehicle is on fire due to the accident, or at least there is the danger exists that it could catch fire."
        "[0016] In one embodiment, reference is made to a state of the battery, designed as a high-voltage battery and/or traction battery, of a vehicle designed as a motor vehicle. This can be an electric vehicle or a hybrid vehicle which, in addition to an electric motor, also has an internal combustion engine for driving purposes."
        "[0017] In a further embodiment, the coded and/or modulated acoustic signals of the loudspeaker are decoded and/or demodulated by a mobile portable terminal which is designed for communication and data processing using software, that is to say an application or app. This software can be installed and executed on the mobile portable terminal at any time. Such a terminal is designed or referred to, for example, as a smartphone or tablet."
        "[0018] The system according to the invention is designed to indicate a state of a battery of a vehicle when or after the vehicle has suffered an accident. In this case, the system has at least one loudspeaker of the vehicle, which is designed to send acoustic signals which include coded items of information about at least one typical current operating parameter of the battery. In addition, a microphone of an external, vehicle-independent terminal is designed to receive the acoustic signals, to decode the coded items of information about the at least one operating parameter of the battery, and to output them in an acoustically and/or visually comprehensible manner to or for a user of the terminal."
        "[0019] For this purpose, it is provided that, depending on the definition, the terminal can be designed as a component of the presented system, wherein this terminal can also be used independently of the system and/or the presented method."
        "[0020] Furthermore, it is possible that the system has a central device, for example a data processing device or a server, which is designed to provide software and thus an application or app that is installable or installed on a processing unit of the terminal device, wherein this software is designed to prompt the terminal to recognize the coded items of information from the acoustic signals provided, to decode them and, on the basis of this, to provide the user with comprehensible explicit items of information about the current state of the battery. A loudspeaker and/or a display panel or display of the terminal is typically used for this purpose. Furthermore, it is possible for the loudspeaker of the vehicle, which is designed to send the coded items of information via the acoustic signals, to be arranged in the vehicle anyway and also to be used for other purposes. However, it is also possible for this loudspeaker to be arranged in the vehicle explicitly as part of the system for carrying out the method."
        "[0021] The presented system is designed to carry out an embodiment of the presented method."
        "[0022] In one embodiment, the system has as a component a control unit of the vehicle, which is designed to detect the at least one typically current operating parameter of the battery, to activate the loudspeaker, and to cause the loudspeaker to send the acoustic signals that comprise the items of coded information regardless of whether or not the acoustic signals are audible or perceptible."
        "[0023] Using the method and the system, it is thus possible to provide the items of information about the state or a status of the battery of the vehicle in case of an accident to the terminal and also to the user via the acoustic signals or a corresponding acoustic channel."
        "[0024] In a further embodiment, it is possible that the acoustic signals having the coded items of information are output directly from the battery, for example, the traction battery, or from the battery as a component of the vehicle, wherein a report about the state after the accident is provided using these items of information. The acoustic signals or a corresponding acoustic output can be implemented with the aid of a loud, recurring beep. In this case, a first responder as the user of the terminal is provided with a clear indication that the battery of the vehicle poses little or no danger. It is additionally possible that the beep is acoustically output proportionally to the state, for example, the state of health, of the battery, which is dependent on the temperature, for example. If there is no danger from the battery, only short loud beeps with short repetitions are provided. However, the more critical the state of the battery becomes, if the battery heats up quickly, for example, the higher a frequency of the beep tones is set, wherein the interval between repetitions of the beeps or of repetitions of the beeps decreases, wherein these beeps are converted into a continuous tone if the battery poses a high or maximum danger. This makes it possible for the user or first responder to be able to better assess the danger without additional aids. Furthermore, the loud beeps can make a vehicle that has gone off of the road during an accident able to be located quickly and easily, if the vehicle, for example, has driven down an embankment and is no longer visible from a road."
        "[0025] The acoustic signals, which are usually designed as beeps and/or alarm tones, the acoustic signals that comprise the detailed items of information about the at least one operating parameter of the battery, for example a respective current value of the temperature, are concealed based on the coding and/or modulation, wherein it is possible that the acoustic signals that carry these items of information can be digitized. These acoustic signals having the items of information about the at least one operating parameter can be received via the application or an app, which is publicly accessible or at least accessible to rescue workers, from the microphone of the mobile terminal, for example a smartphone, usually recognized as such, demodulated and decoded and, and furthermore clear and comprehensible items of information can be acoustically and/or optically represented, wherein these clear items of information comprise, for example, a physical value of the temperature as the at least one operating parameter of the battery. It is thus possible, for example, for a rescue worker as a user to be informed of the operating state of the battery and thus of a specific danger, whereby the user can better assess the risk."
        "[0026] In this embodiment, it is possible that the audible beeps or alarm tones already comprise the coded items of information about the at least one operating parameter of the battery. The beeps or alarm tones can be at least partially digital and, for example, can have a structure similar to tones as they were used in the 1980s on music cassettes or so-called datasettes for storing data for home computers."
        "[0027] It is possible that in the battery, for example a traction battery, an acoustic actuator is installed as a loudspeaker, so that the loudspeaker is not only designed as a component of the vehicle, but also directly as a component of the battery. The loudspeaker is usually activated via an internal control unit, for example by a battery management system (BMS). It is possible here that a hazard indicator is calculated by the control unit on the basis of an algorithm, using which the at least one, usually internal, operating state of the battery, that is to say the temperature or cell temperature and/or the voltage or cell voltage, and, for example, an acceleration of the vehicle that occurred before the accident is taken into consideration. With this hazard indicator, a specific danger of the battery, which is caused by the battery, can be taken into consideration. This is possible, for example, in the event that the battery is on the verge of a thermal runaway. An acoustic warning tone is provided as an acoustic signal from a certain danger level if the hazard indicator determines that the at least one operating parameter of the battery exceeds a predetermined critical value, wherein the warning tone is caused to be output by the built-in loudspeaker, for example. The hazard indicator or corresponding information can also be coded and modulated."
        "[0028] It is possible that the volume and/or frequency of the warning tone is usually set in direct proportion to the danger level. The greater the danger level, the louder the warning tone and the higher the frequency, which means that the intervals between individual beeps are reduced. The acoustic and thus usually audible signals can have different signal forms and do not necessarily have to be designed as beeps. The system and the loudspeaker are only activated after the accident has been recognized for the vehicle, usually by its control unit."
        "[0029] It is apparent that the above-mentioned features and the features still to be explained hereinafter are usable not only in the particular specified combination but rather also in other combinations or alone, without leaving the scope of the present invention."
    )
    # # Clean, isolated invention disclosure completely free of python syntax characters
    # test_disclosure = (
    #     "Vehicle's loudspeaker,details:Used for sending acoustic signals"
    #     "Terminal's microphone,details:Used for receiving acoustic signals"
    #     "Terminal,details:Used for decoding and displaying the decoded information"
    #     "Sending acoustic signals by the vehicle's loudspeaker"
    #     "Includes coded items of information about at least one operating parameter of the battery"
    #     "Transmitting battery state information"
    # )

    # 2. Discrete Feature Segmentation
    struct_feat = "vehicle, battery pack, operational parameters sensors, acoustic loudspeaker, hardware terminal, microphone, decoder matrix."
    proc_feat = (
        "detecting vehicle accident, measuring battery parameters data values, encoding items of information, transmitting sonic audio signals, receiving sound waves, decoding transmission frames."
    )
    func_feat = "indicating operating state of a battery during post-crash emergency boundaries via acoustic transmission over-the-air bypassing cellular radio frequency networks."

    print("\n--- Running Multi-Pass Specialized Facet Vector Fusion ---")
    recommendations = engine.recommend_multi_pass(full_abstract=abstract, structural=struct_feat, procedural=proc_feat, functional=func_feat, top_k=15)

    print("\n=== TOP RECOMMENDED CPC PRIOR ART CLASSIFICATIONS ===")
    for rank, rec in enumerate(recommendations, start=1):
        print(f"\nRANK {rank} [Score: {rec['confidence_score']:.4f}]")
        print(f"👉 CPC CODE: {rec['cpc_code']}")
        print(f"👉 TITLE: {rec['title']}")
        print("-" * 50)
