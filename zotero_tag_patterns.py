# SUPPLEMENTARY_TAG_MAPPING.py
# Complete tag mapping for all 131 items in cUAS_AD.json
# Includes dissertation-relevant AND non-dissertation items

TAG_MAPPING = {
    # =========================================================================
    # DISSERTATION-RELEVANT: Article 1 Categories
    # =========================================================================
    
    # 01a - Prior FAA UAS Analysis (foundational UAS sighting studies)
    r'^wang.*(characteristics|investigating|threats).*': '#A1-01a-Prior',
    r'^howard.*faa.*unmanned': '#A1-01a-Prior',
    r'^das.*exploratory': '#A1-01a-Prior',
    r'^pitcher': '#A1-01a-Prior',
    r'^gettinger.*drone.*sightings': '#A1-01a-Prior',
    r'^akers.*drone.*sight': '#A1-01a-Prior',
    r'^sharma.*investigation.*unmanned': '#A1-01a-Prior',
    r'^greenewald.*faa.*unmanned': '#A1-01a-Prior',
    r'^pascarella.*historical.*drone': '#A1-01a-Prior',
    r'^sun.*examination.*uas': '#A1-01a-Prior',
    r'^kashyap.*analyzing.*trends.*uas': '#A1-01a-Prior',
    
    # 01b - Aviation Safety Text Analysis
    r'^kuhn.*structural.*topic': '#A1-01b-TextAnalysis',
    r'^rose.*structural.*topic': '#A1-01b-TextAnalysis',
    r'^dou.*navigating.*massive': '#A1-01b-TextAnalysis',
    r'^darveau.*automated.*classification': '#A1-01b-TextAnalysis',
    r'^luo.*lda2vec': '#A1-01b-TextAnalysis',
    r'^paradis.*augmenting.*topic': '#A1-01b-TextAnalysis',
    r'^nanyonga.*topic.*modeling': '#A1-01b-TextAnalysis',
    
    # 02a - LLM Aviation Applications
    r'^tikayatray.*generative': '#A1-02a-LLM-Aviation',
    r'^basil.*large.*language': '#A1-02a-LLM-Aviation',
    r'^andrade.*safeaerobert': '#A1-02a-LLM-Aviation',
    r'^chen.*information.*extraction.*aviation': '#A1-02a-LLM-Aviation',
    r'^siddeshwar.*aviation.*safety': '#A1-02a-LLM-Aviation',
    r'^ziakkas.*artificial.*intelligence': '#A1-02a-LLM-Aviation',
    r'^liu.*large.*language.*air.*transport': '#A1-02a-LLM-Aviation',
    r'^martin-domingo.*extracting.*airline': '#A1-02a-LLM-Aviation',
    
    # 02b - LLM/NLP Methods (general, not aviation-specific)
    r'^agrawal.*large.*language.*clinical': '#A1-02b-LLM-Methods',
    r'^xu.*large.*language.*generative': '#A1-02b-LLM-Methods',
    r'^wang.*gptner': '#A1-02b-LLM-Methods',
    r'^tjongkimsang.*conll': '#A1-02b-LLM-Methods',
    
    # 02c - Prompt Engineering
    r'^brown.*language.*models.*are': '#A1-02c-Prompt',
    r'^wei.*chain.*thought': '#A1-02c-Prompt',
    r'^liu.*pretrain.*prompt': '#A1-02c-Prompt',
    r'^min.*rethinking.*demonstrations': '#A1-02c-Prompt',
    r'^chen.*evaluation.*prompt': '#A1-02c-Prompt',
    r'^reynolds.*prompt.*programming': '#A1-02c-Prompt',
    r'^zamfirescu.*johnny': '#A1-02c-Prompt',
    
    # 03 - Fine-Tuning
    r'^howard.*universal.*language': '#A1-03-FineTune',
    r'^hu.*lora': '#A1-03-FineTune',
    r'^dettmers.*qlora': '#A1-03-FineTune',
    r'^majdik.*sample.*size.*fine.*tuning': '#A1-03-FineTune',
    
    # 04a - Inter-Rater Reliability
    r'^gwet.*handbook': '#A1-04a-IRR',
    r'^sim.*kappa': '#A1-04a-IRR',
    r'^landis.*koch': '#A1-04a-IRR',
    r'^donner.*eliasziw': '#A1-04a-IRR',
    
    # 04b - Sample Size / Power Analysis
    r'^leon.*sample.*sizes': '#A1-04b-SampleSize',
    r'^gelman.*16.*times': '#A1-04b-SampleSize',
    
    # 04c - Statistical Foundations
    r'^firth.*bias.*reduction': '#A1-04c-Stats',
    r'^heinze.*solution.*problem.*separation': '#A1-04c-Stats',
    r'^king.*logistic.*regression.*rare': '#A1-04c-Stats',
    r'^peduzzi.*simulation': '#A1-04c-Stats',
    r'^puhr.*firth': '#A1-04c-Stats',
    r'^vittinghoff.*relaxing': '#A1-04c-Stats',
    r'^tibshirani.*regression.*shrinkage': '#A1-04c-Stats',
    r'^snijders.*multilevel': '#A1-04c-Stats',
    
    # 05a - Time Series / Forecasting
    r'^cleveland.*stl.*seasonal': '#A1-05a-TimeSeries',
    r'^hyndman.*forecasting': '#A1-05a-TimeSeries',
    r'^wang.*characteristic.*based.*clustering.*time': '#A1-05a-TimeSeries',
    
    # 05b - Changepoint Detection
    r'^killick.*(optimal|changepoint)': '#A1-05b-Changepoint',
    
    # 05c - Lexical Diversity
    r'^mccarthy.*mtld': '#A1-05c-LexDiv',
    r'^covington.*gordian': '#A1-05c-LexDiv',
    
    # 06 - Human Factors
    r'^wiegmann.*human.*error': '#A1-06-HumanFactors',
    
    # 07 - Safety Context (UAS detection, pilot studies, NMAC)
    r'^wallace': '#A1-07-Safety',
    r'^loffi.*seeing.*threat': '#A1-07-Safety',
    r'^vance.*detecting.*assessing': '#A1-07-Safety',
    r'^baum.*improving.*cockpit': '#A1-07-Safety',
    r'^may.*review.*collisions.*drones': '#A1-07-Safety',
    r'^gao.*dynamics.*voluntary': '#A1-07-Safety',
    r'^kioulepoglou.*investigating.*incident': '#A1-07-Safety',
    
    # 08 - UAS Risk Assessment / Regulation
    r'^breunig.*modeling.*risk': '#A1-08-RiskReg',
    r'^nikodem.*specific.*operations.*risk': '#A1-08-RiskReg',
    r'^denney.*rigorous.*basis': '#A1-08-RiskReg',
    r'^schnuriger.*sora.*tool': '#A1-08-RiskReg',
    r'^hunter.*family.*based.*safety': '#A1-08-RiskReg',
    r'^mandourah.*violation.*drone': '#A1-08-RiskReg',
    r'^truong.*(enhance.*safety|machine.*learning)': '#A1-08-RiskReg',
    r'^cleland.*huang.*real.*time': '#A1-08-RiskReg',
    r'^puranik.*online.*prediction': '#A1-08-RiskReg',
    r'^rao.*state.*based': '#A1-08-RiskReg',
    r'^asghari.*uav.*operations.*safety': '#A1-08-RiskReg',
    r'^gohar.*engineering.*fair': '#A1-08-RiskReg',
    
    # =========================================================================
    # NON-DISSERTATION: Filter/Move Categories
    # =========================================================================
    
    # Counter-UAS Technology & Systems
    r'^abdulhadi.*counter.*uas': '#NonDiss-cUAS-Tech',
    r'^gabor.*no.*drone': '#NonDiss-cUAS-Tech',
    r'^lykou.*defending.*airports': '#NonDiss-cUAS-Tech',
    r'^park.*survey.*anti.*drone': '#NonDiss-cUAS-Tech',
    r'^stary.*evaluation.*counter': '#NonDiss-cUAS-Tech',
    r'^grieco.*detection.*tracking': '#NonDiss-cUAS-Tech',
    r'^kim.*study.*development.*counter': '#NonDiss-cUAS-Tech',
    r'^pettyjohn.*countering.*swarm': '#NonDiss-cUAS-Tech',
    r'^yang.*intellectual.*structure.*counter': '#NonDiss-cUAS-Tech',
    
    # Dark Drones / Non-Cooperative UAS
    r'^asis.*dark.*drones': '#NonDiss-DarkDrone',
    r'^caci.*spark.*dark': '#NonDiss-DarkDrone',
    r'^defencexp.*dark.*drones': '#NonDiss-DarkDrone',
    r'^echodyne.*dark.*drone': '#NonDiss-DarkDrone',
    r'^dhs.*dark.*drone': '#NonDiss-DarkDrone',
    r'^nasa.*coop.*noncoop': '#NonDiss-DarkDrone',
    r'^epstein.*russia.*unjammable': '#NonDiss-DarkDrone',
    
    # DHS/Government cUAS Programs
    r'^dhs.*cuas': '#NonDiss-DHS-cUAS',
    r'^dhs.*air.*domain': '#NonDiss-DHS-cUAS',
    r'^idga.*dhs.*cuas': '#NonDiss-DHS-cUAS',
    r'^dronelife.*ndaa.*cuas': '#NonDiss-DHS-cUAS',
    r'^department.*defense.*counter': '#NonDiss-DHS-cUAS',
    r'^research.*development.*acquisition.*counter': '#NonDiss-DHS-cUAS',
    r'^usarmy.*sbir': '#NonDiss-DHS-cUAS',
    r'^how.*us.*confronting': '#NonDiss-DHS-cUAS',
    
    # Detection/Radar Systems (vendor/product focused)
    r'^quickset.*drone.*detection': '#NonDiss-Detection',
    r'^robinradar.*counter.*drone': '#NonDiss-Detection',
    r'^spotterglobal.*radar': '#NonDiss-Detection',
    
    # Regulatory Documents (FAA/CFR - reference only)
    r'^14cfrpart': '#NonDiss-Regulatory',
    r'^assure.*faa.*center': '#NonDiss-Regulatory',
    r'^drone.*sightings.*airports': '#NonDiss-Regulatory',
    r'^remote.*identification.*drones': '#NonDiss-Regulatory',
    
    # News/Current Events
    r'^jacobsen.*drone.*sightings.*disrupt': '#NonDiss-News',
    r'^posard.*not.*files': '#NonDiss-News',
    r'^challenges.*investigating.*mid.*air': '#NonDiss-News',
    
    # Urban Air Mobility / Future Concepts (not Article 1 scope)
    r'^straubinger.*overview.*urban': '#NonDiss-UAM',
    r'^oshea.*closing.*gaps': '#NonDiss-UAM',
}

# Catch-all: Items not matching any pattern get this tag
DEFAULT_TAG = '#Review-Uncategorized'
