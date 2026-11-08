"""Tau ID + tau energy scale (ES) datacard producer.

Python version of TauIDSFMeasurement/bin/MorphingTauID2017.cpp (branch tauID_ES),
in one file.  Usage from another script:

    from CombineHarvester.TauIDSFSimple import produce_datacards
    cb, ws = produce_datacards(era="2018", category="DM0", base_path="/path/to/shapes")

Command line: scripts/morphing_tauid.py (same option names as the C++ program).

Physics in short: in the mu-tau_h channel ("mt") one tau decay-mode category is
fitted per run.  The signal is the embedded Z->tautau sample "EMB_<category>".
Its templates exist for a grid of ES shifts; they are morphed into one pdf that
depends on the RooRealVar "ES_<category>" (the fitted ES shift in %).  The tau
ID scale factor is the signal normalisation.  An optional mu-mu control region
("mm", no signal) constrains the muon related normalisations.
"""

import os
from math import fmod, sqrt

import cppyy
import ROOT

from CombineHarvester.CombineTools import ch

cppyy.load_reflection_info("libCombineHarvesterCombinePdfs")  # for CMSHistFuncFactory

ERA_TAGS = {"2016preVFP": "Run2016preVFP", "2016postVFP": "Run2016postVFP",
            "2017": "Run2017", "2018": "Run2018", "2024": "Run2024"}

# Category name -> bin id (ids as in the C++ code).  The C++ also listed "all",
# "Pt*" and "Inclusive", but they crashed there, so they are left out.
CATEGORIES = {name: 7 + i for i, name in enumerate(
    [dm + pt for pt in ["", "_PT20_40", "_PT40_200"]
     for dm in ["DM0", "DM1", "DM1011", "DM10", "DM11"]])}

# Embedded processes that get the muon / embedding uncertainties, copied 1:1
# from the C++.  NOTE: "EMB_DM10" and "EMB_DM11" are missing there, so these
# two categories get no such uncertainties on the signal (probably a bug).
EMB_PROCESSES = [
    "EMB_Pt20to25", "EMB_Pt25to30", "EMB_Pt30to35", "EMB_Pt35to40", "EMB_PtGt40",
    "EMB_DM0", "EMB_DM1", "EMB_DM1011", "EMB_Inclusive", "MUEMB",
    "EMB_DM0_PT20_40", "EMB_DM1_PT20_40", "EMB_DM1011_PT20_40", "EMB_DM10_PT20_40", "EMB_DM11_PT20_40",
    "EMB_DM0_PT40_200", "EMB_DM1_PT40_200", "EMB_DM1011_PT40_200", "EMB_DM10_PT40_200", "EMB_DM11_PT40_200",
]
LUMI = {"Run2016preVFP": 1.012, "Run2016postVFP": 1.012, "Run2017": 1.0082, "Run2018": 1.0084, "Run2024": 0.0161} # Run3 source: https://twiki.cern.ch/twiki/bin/viewauth/CMS/LumiRecommendationsRun3#2024
JES_SOURCES = [
    "Total", "SinglePionECAL", "SinglePionHCAL", "AbsoluteMPFBias", "AbsoluteScale",
    "Fragmentation", "PileUpDataMC", "RelativeFSR", "PileupPtRef", "AbsoluteStat",
    "TimePtEta", "RelativeStatFSR", "FlavorQCD", "PileupPtEC1", "PileUpPtBB",
    "RelativePtBB", "RelativeJEREC1", "RelativePtEC1", "RelativeStatEC", "RelativePtHF",
    "PileUpPtHF", "RelativeJERHF", "RelativeStatHF", "PileUpPtEC2", "RelativeJEREC2",
    "RelativePtEC2", "RelativeBal", "RelativeSample",
]
BASE_PATH_DEFAULT = os.path.join(os.environ.get("CMSSW_BASE", "."), "src/CombineHarvester/TauIDSFMeasurement/shapes")


def es_shifts(es_min, es_max, tes_precision):
    """ES grid labels '-8.0' ... '8.0' without '0.0' (integer steps: no float drift)."""
    n_min, n_max = round(es_min / tes_precision), round(es_max / tes_precision)
    return [f"{n * tes_precision:.1f}" for n in range(n_min, n_max + 1) if n != 0]


def add_systematics(cb, era_tag, embedding):
    """Add the uncertainty model (v15).  Shape nuisances read <proc>_<name>Up/Down
    from the input file; $ERA/$CHANNEL make a nuisance uncorrelated per era/channel."""
    def add(channels, procs, name, kind, value):
        cb.cp().channel(channels).process(procs).AddSyst(cb, name, kind, ch.SystMap()(float(value)))

    # set a flag if this is a Run3 era
    run3 = era_tag in ["Run2024"]  
    
    if embedding:  # genuine taus come from the embedded sample, not from MC
        mc = ["TTL", "TTJ", "W", "ZJ", "ZL", "VVL", "VVJ", "STL", "STJ"]
    else:
        mc = ["ZTT", "TTT", "TTL", "TTJ", "W", "ZJ", "ZL", "VVT", "VVL", "VVJ", "STT", "STL", "STJ"]

    add(["mt", "mm"], mc, "lumi_13TeV_$ERA", "lnN", LUMI[era_tag])
    
    # Run2 Prefiring Unerctainty: https://twiki.cern.ch/twiki/bin/viewauth/CMS/L1PrefiringWeightRecipe
    if not run3 and era_tag != "Run2018":
        add(["mt"], mc, "CMS_prefiring", "shape", 1.0)

    # Muon trigger/ID/iso: separate for MC and embedding, 4% in mm (two muons).
    add(["mt"], mc, "CMS_eff_m_trigger_$ERA", "shape", 1.0)
    # For Run3 the muon trigger ID/ISO/trigger uncertainties are derived from the SF measurement itself and is not a fiexed 4% uncertainty.
    if run3:
        for name in ["id", "iso"]:
            add(["mt", "mm"], EMB_PROCESSES, f"CMS_eff_m_{name}_emb_$ERA", "shape", 1.0)
            add(["mt", "mm"], mc, f"CMS_eff_m_{name}_$ERA", "shape", 1.0)
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_trigger_emb_$ERA", "shape", 1.0)
    else:
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_trigger_emb_$ERA", "lnN", 1.02)
        for name in ["id", "iso"]:
            add(["mt"], EMB_PROCESSES, f"CMS_eff_m_{name}_emb", "lnN", 1.02)
            add(["mm"], EMB_PROCESSES, f"CMS_eff_m_{name}_emb", "lnN", 1.04)
            add(["mt"], mc, "CMS_eff_m_" + name, "lnN", 1.02)
            add(["mm"], mc, "CMS_eff_m_" + name, "lnN", 1.04)

    # Tau ID and ES of simulation. The embedded signal's ID and ES are what we measure, so they get no nuisance here.
    for dm in ["dm0", "dm1", "dm10", "dm11"]:
        add(["mt"], ["ZTT", "TTT", "TTL", "VVT", "VVL", "STT", "STL"], f"CMS_eff_t_{dm}_$ERA", "shape", 1.0)
        add(["mt"], ["ZTT", "TTT", "TTL", "VVT", "VVL", "STT", "STL"], f"CMS_scale_t_{dm}_$ERA", "shape", 1.0)

    for source in JES_SOURCES:
        add(["mt"], mc, "CMS_scale_j_" + source, "shape", 1.0)
    
    # HEM issue in 2018
    if era_tag == "Run2018":
        add(["mt"], mc, "CMS_scale_j_HEMIssue_$ERA", "shape", 1.0)

    # MET energy scale and recoil
    add(["mt"], ["ZTT", "TT", "TTT", "TTL", "TTJ", "W", "ZJ", "ZL", "VV", "VVT", "VVL", "VVJ",
                 "STT", "STL", "STJ"], "CMS_scale_met_unclustered_energy_$ERA", "shape", 1.0)
    add(["mt"], ["ZTT", "ZL", "ZJ", "W"], "CMS_scale_met_$ERA", "shape", 1.0)
    add(["mt"], ["ZTT", "ZL", "ZJ", "W"], "CMS_res_met_$ERA", "shape", 1.0)

    # Cross sections (Background normalisations)
    add(["mt", "mm"], ["VVT", "VVJ", "VVL", "VV"], "CMS_htt_vvXsec", "lnN", 1.06)       # VV
    add(["mt", "mm"], ["TTT", "TTL", "TTJ", "TT"], "CMS_htt_tjXsec", "lnN", 1.055)      # TT
    add(["mt", "mm"], ["STT", "STL", "STJ", "ST"], "CMS_htt_stXsec", "lnN", 1.055)      # ST
    add(["mt", "mm"], ["W"], "CMS_htt_wjXsec", "lnN", 1.05)                             # W
    if embedding:
        add(["mt", "mm"], ["ZL", "ZJ"], "CMS_htt_zjXsec", "lnN", 1.04)                  # Z (emb) 4% (estimated)
    else:  # free Drell-Yan normalisation, constrained by the mm region
        add(["mt"], ["ZTT", "ZL", "ZJ"], "CMS_htt_zjXsec", "rateParam", 1.0)            # Z (MC) rateParam -> constrained by mm region
        add(["mm"], ["ZLL"], "CMS_htt_zjXsec", "rateParam", 1.0)                        # Z (MC) rateParam -> constrained by mm region
    add(["mt", "mm"], ["QCD", "QCDEMB"], "CMS_ExtrapSSOS_$CHANNEL_$ERA", "lnN", 1.30)   # QCD

    # TT shape reweighting
    add(["mt"], ["TTT", "TTL", "TTJ", "TT"], "CMS_htt_ttbarShape", "shape", 1.0)
    
    # Muon -> tau_h fakes: ES of the fake and fake-rate SFs in 5 eta (wheel) regions.
    add(["mt"], ["ZL"], "CMS_scale_fake_m_$ERA", "shape", 1.0)
    for i in range(1, 6):
        add(["mt"], ["ZL"], f"CMS_fake_m_WH{i}_$ERA", "shape", 1.0)
    # Jet -> tau_h fakes:
    add(["mt"], ["W", "TTJ", "ZJ", "VVJ"], "CMS_fake_j_$ERA", "shape", 1.0)

    ## Embedding-specific uncertainties:
    # Embedding selection trigger efficiency
    if run3:
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_emb_selection_trigger_$ERA", "shape", 1.0) # For Run3 those come from the SF measurement itself
    else:
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_emb_selection_trigger_$ERA", "lnN", 1.04)
    # estimate the contamination of ttbar events in the embedded sample. 10% shape uncertainty of assumed ttbar->tautau event shape  // this should be included to input ntuples
    add(["mt"], EMB_PROCESSES, "CMS_emb_ttbar_contamination_$ERA", "shape", 1.0)


def produce_datacards(era="2018", category="DM0", es_min=-8.0, es_max=8.0, tes_precision=0.1,
                      base_path=BASE_PATH_DEFAULT,
                      input_folder_mt="Vienna/", input_folder_mm="Vienna/", postfix="-ML",
                      output_folder="sm_run2", output_dir="output",
                      jetfakes=True, embedding=False, use_control_region=True, real_data=False,
                      auto_rebin=False, manual_rebin_for_yields=False,
                      classic_bbb=False, binomial_bbb=False, write=True, verbose=False):
    """Build the model, read the templates, morph the signal, write the cards.

    Returns (cb, ws): the CombineHarvester and the morphing RooWorkspace
    (keep ws alive while using cb).  Defaults are those of the C++ program.
    """
    if era not in ERA_TAGS:
        raise ValueError(f"Unknown era '{era}', use one of {list(ERA_TAGS)}")
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}', use one of {list(CATEGORIES)}")
    if tes_precision <= 0 or abs(tes_precision * 10 - round(tes_precision * 10)) > 1e-6:
        raise ValueError("tes_precision must be a multiple of 0.1 (ES labels have one decimal)")
    era_tag = ERA_TAGS[era]
    signal = "EMB_" + category
    bin_id = CATEGORIES[category]
    channels = ["mt", "mm"] if use_control_region else ["mt"]

    # --- 1. processes ---------------------------------------------------------
    # Background names: Z/TT/ST/VV + T (genuine tau), L (lepton->tau), J (jet->tau).
    mt_bkgs = ["W", "QCD", "ZL", "ZJ", "TTT", "TTL", "TTJ", "STT", "STL", "STJ", "VVJ", "VVT", "VVL"]
    if embedding:  # genuine taus are in the embedded sample, so remove them from the MC backgrounds
        mt_bkgs = [p for p in mt_bkgs if p not in ["TTT", "STT", "VVT"]]
    if jetfakes:  # all jet->tau backgrounds come from the fake-factor method, so remove them from the MC backgrounds and add the jetFakes process
        mt_bkgs = [p for p in mt_bkgs if p not in ["QCD", "W", "VVJ", "TTJ", "STJ", "ZJ"]] + ["jetFakes"]
    bkgs = {"mt": mt_bkgs, "mm": ["W", "TTL", "VVL", "QCD", "MUEMB"]}
    cats = {"mt": [(bin_id, "mt_" + category)], "mm": [(100, "mm_control_region")]}

    cb = ch.CombineHarvester()
    if verbose:
        cb.SetVerbosity(1)
    # Add the observations (data) and the processes (signal and backgrounds MC). The signal is the embedded sample, which has one template per ES shift.
    for chn in channels:
        cb.AddObservations(mass=["*"], analysis=["htt"], era=[era_tag], channel=[chn], bin=cats[chn])
        cb.AddProcesses(mass=["*"], analysis=["htt"], era=[era_tag], channel=[chn],
                        procs=bkgs[chn], bin=cats[chn], signal=False)
    # The signal's "mass" is the ES shift: one template per grid point.
    cb.AddProcesses(mass=es_shifts(es_min, es_max, tes_precision), analysis=["htt"], era=[era_tag],
                    channel=["mt"], procs=[signal], bin=cats["mt"], signal=True)

    # --- 2. systematics -------------------------------------------------------
    add_systematics(cb, era_tag, embedding)

    # --- 3. templates from file ----------------------------------------------
    for chn in channels:
        folder = input_folder_mt if chn == "mt" else input_folder_mm
        path = os.path.join(base_path, folder, f"htt_{chn}.inputs-sm-{era_tag}{postfix}.root")
        cb.cp().channel([chn]).backgrounds().ExtractShapes(path, "$BIN/$PROCESS", "$BIN/$PROCESS_$SYSTEMATIC")
        if chn == "mt":
            cb.cp().channel([chn]).signals().ExtractShapes(path, "$BIN/$PROCESS_$MASS", "$BIN/$PROCESS_$MASS_$SYSTEMATIC")

    # --- 4. template treatment -----------------------------------------------
    # Empty processes/templates make combine fail: drop them (and their systematics).
    empty = set()
    cb.ForEachProc(lambda p: empty.add((p.bin(), p.process(), p.mass())) if not p.rate() > 0 else None)
    print(f"[INFO] Dropping {len(empty)} empty processes/templates: {empty}")
    cb.FilterProcs(lambda p: (p.bin(), p.process(), p.mass()) in empty)
    cb.FilterSysts(lambda s: (s.bin(), s.process(), s.mass()) in empty
                   or (s.type() == "shape" and (s.shape_u().Integral() == 0 or s.shape_d().Integral() == 0))) # Delete systematics with 0 yield since these result in a bogus norm error in combine

    # Replacing observation with the sum of the backgrounds (Asimov data) useful to be able to check this, so don't do the replacement for these
    if not real_data:
        # Asimov data = sum of all templates. This includes ALL
        # ES-shifted signal templates, so it is far too large; for a proper Asimov
        # fit use real_data=True and combine's "-t -1".
        for b in cb.bin_set():
            print(f"[INFO] Replacing observation in {b} with sum of all MC shapes (Asimov data)")
            total = cb.cp().bin([b]).backgrounds().GetShape()
            total.Add(cb.cp().bin([b]).signals().GetShape())
            cb.cp().bin([b]).ForEachObs(lambda obs: obs.set_shape(total, True))

    # Shapes are stored with unit area; when replacing them keep rate / value_u / value_d.
    def set_syst_shapes(s, h_u, h_d):
        value_u, value_d = s.value_u(), s.value_d()
        s.set_shapes(h_u, h_d, h_u)
        s.set_value_u(value_u)
        s.set_value_d(value_d)

    def zero_negative(p):  # negative bins from negative MC weights
        """Set negative bins in the shape to zero."""
        
        if cppyy.gbl.ch.HasNegativeBins(p.shape()):
            h = p.ClonedShape()
            cppyy.gbl.ch.ZeroNegativeBins(h.get())
            p.set_shape(h, False)

    def zero_negative_syst(s):
        """Set negative bins in the up and down shapes of a the systematic uncertainties to zero."""
        if "shape" in s.type() and (cppyy.gbl.ch.HasNegativeBins(s.shape_u())
                                    or cppyy.gbl.ch.HasNegativeBins(s.shape_d())):
            h_u, h_d = s.ClonedShapeU(), s.ClonedShapeD()
            cppyy.gbl.ch.ZeroNegativeBins(h_u.get())
            cppyy.gbl.ch.ZeroNegativeBins(h_d.get())
            set_syst_shapes(s, h_u, h_d)

    cb.ForEachProc(zero_negative)
    cb.ForEachSyst(zero_negative_syst)

    # auto rebinning
    if auto_rebin:
        THRESHOLD = 1.0  # minimum number of background events per bin
        TOLERANCE = 1e-4  # numerical tolerance for the modulo operation
        # Same algorithm as the C++ (MorphingTauID2017.cpp), including its quirks.
        #
        # It was written for "unrolled" NN-score histograms: several slices of a
        # score axis [offset, 1.0] placed next to each other, e.g. for offset 0.2:
        #
        #     slice 0      slice 1      slice 2
        #   |-----------|------------|-----------|
        #  0.2         1.0          1.8         2.6     slice width = 1.0 - offset
        #
        # Bins are merged from right to left until each has > THRESHOLD background
        # events, but never across a slice border (offset + k * width).
        #
        # For a plain 1D histogram starting above 1 (e.g. m_vis 20...200 GeV) the
        # "width" 1 - offset is negative (-19).  The only border that usually
        # matches is then the first edge (20), so in practice the algorithm becomes
        # "merge from the right until each bin has > 1 event".
        for b in cb.bin_set():
            shape = cb.cp().bin([b]).backgrounds().GetShape()
            n = shape.GetNbinsX()
            offset = shape.GetBinLowEdge(1)  # lower edge of the first bin (e.g. 0.2 for NN scores, 20 for m_vis)
            width = 1.0 - offset  # assumed width of one unrolled slice

            def is_border(x, offset=offset, width=width):
                # x lies on offset + k * width.  fmod (not %) to match C++.
                # width == 0 (offset = 1): C++ fmod gives NaN, so nothing is a border.
                return width != 0 and abs(fmod(x - offset, width)) < TOLERANCE

            edges = [shape.GetBinLowEdge(n + 1)]  # start with the upper edge of the last bin
            content = 0.0  # background yield collected since the last kept edge
            for i in range(n, 0, -1):  # right to left
                low_edge = shape.GetBinLowEdge(i)
                content += shape.GetBinContent(i)
                if is_border(low_edge):
                    # A border always becomes an edge.  If the bin that ends here is
                    # still too small, merge it into its right neighbour instead, by
                    # removing the edge between them -- unless that edge is a border too.
                    #
                    #   before:  border |0.8 events| e |2.5 events| ...
                    #   after:   border |   3.3 events   | ...      (edge e removed)
                    #
                    # The C++ condition, !(A || B) with B = |fmod(..)| - width < tol,
                    # has a misplaced parenthesis: B is always true for width > 0 and
                    # always false for width < 0.  So this merge only happens for
                    # width < 0, i.e. histograms that start above 1 (like m_vis).
                    # len(edges) > 1: never remove the upper edge of the histogram
                    # (the C++ would do that if the whole histogram has <= 1 event).
                    if content <= THRESHOLD and width < 0 and not is_border(edges[0]) and len(edges) > 1:
                        edges.pop(0)
                    edges.insert(0, low_edge)
                    content = 0.0
                elif content > THRESHOLD:  # enough events collected: close this bin
                    edges.insert(0, low_edge)
                    content = 0.0
            cb.cp().bin([b]).VariableRebin(edges)
        # Blind bins that are still below THRESHOLD background events: remove their
        # content from all processes, data and shape systematics.
        #
        # NOTE: deliberately different from the C++ (MorphingTauID2017.cpp), which
        # zeroes the bin in ClonedShape() and calls set_shape(h, false).  CH stores
        # shapes at unit area and set_shape(h, false) keeps the old rate, so the
        # shape is renormalised and the blinded events are pushed into the other
        # bins instead of being removed, with a different factor per process:
        #
        #   before          bin: [0.2 | 5    | 10   | 5   ]  rate 20.2
        #   C++ blinding         [0   | 5.05 | 10.1 | 5.05]  rate 20.2  (+1 %)
        #   ZeroBins             [0   | 5    | 10   | 5   ]  rate 20.0
        #
        # That distorts the shapes (also of the signal, which the threshold does not
        # look at) and can bias the fitted SF and ES.  ch::CombineHarvester::ZeroBins
        # does it correctly: it zeroes the bin in the scaled histograms, sets the new
        # rates, and recalculates value_u/value_d of the shape systematics from the
        # blinded nominal.  It blinds every bin lying fully inside [min, max].
        # So with auto_rebin the cards differ from the C++ ones.
        for b in cb.bin_set():
            shape = cb.cp().bin([b]).backgrounds().GetShape()
            for i in range(1, shape.GetNbinsX() + 1):
                if shape.GetBinContent(i) < THRESHOLD:
                    print(f"[INFO] Blind bin {i} in {b}")
                    cb.cp().bin([b]).ZeroBins(shape.GetBinLowEdge(i), shape.GetBinLowEdge(i + 1))

    if manual_rebin_for_yields:  # one bin: only the yields remain
        for b in cb.bin_set():
            cb.cp().bin([b]).VariableRebin([0.0, 1.0])

    # Merge bins and set bin-by-bin uncertainties if no autoMCStats is used.
    if classic_bbb:
        bbb = ch.BinByBinFactory()
        bbb.SetAddThreshold(0.0).SetMergeThreshold(0.5).SetFixNorm(False)
        bbb.MergeBinErrors(cb.cp().backgrounds())
        bbb.AddBinByBin(cb.cp().backgrounds(), cb)

    if binomial_bbb:
        # Embedded events are re-used with a kinematic filter (efficiency p, n trials):
        # bin error = sqrt(x p/n (1-p)).  One shape nuisance per bin that moves only that bin.
        # The C++ applied this to the non-existing "em" channel; here to the mt signal.
        p_filter, n_trials = 0.022, 1000.0
        procs = []
        cb.cp().channel(["mt"]).process([signal]).ForEachProc(lambda p: procs.append(p))
        for proc in procs:
            h = proc.shape()
            if h.GetSumw2N() == 0:
                print(f"[WARNING] {proc.process()} has no bin errors, no binomial bbb")
                continue
            for j in range(1, h.GetNbinsX() + 1):
                err = sqrt(h.GetBinContent(j) * p_filter / n_trials * (1.0 - p_filter))
                h_u, h_d = h.Clone(), h.Clone()
                h_u.SetBinContent(j, h.GetBinContent(j) + err)
                h_d.SetBinContent(j, max(h.GetBinContent(j) - err, 0.0))
                if not h_d.Integral() > 0:
                    h_d.SetBinContent(j, 1e-5 * h.Integral())
                s = ch.Systematic()
                for attr in ["bin", "process", "signal", "analysis", "era", "channel", "bin_id", "mass"]:
                    getattr(s, "set_" + attr)(getattr(proc, attr)())
                s.set_all_attributes(proc.all_attributes())
                s.set_type("shape")
                s.set_asymm(True)
                s.set_name(f"CMS_htt_{proc.channel()}_{proc.bin()}_{era_tag}_{proc.process()}_binomial_bin_{j}")
                s.set_shapes(h_u, h_d, h)  # also sets value_u/d = integral ratios
                cb.CreateParameterIfEmpty(s.name())
                cb.InsertSystematic(s)

    # this function modifies every entry to have a standardised bin name of the form: {analysis}_{channel}_{bin_id}_{era}
    ch.SetStandardBinNames(cb, "$ANALYSIS_$CHANNEL_$BINID_$ERA")  # e.g. htt_mt_7_Run2018
    cb.SetAutoMCStats(cb, 10.0) # activate combine's autoMCStats (https://cms-analysis.github.io/HiggsAnalysis-CombinedLimit/latest/part2/bin-wise-stats/) with a threshold of 10 events per bin

    # --- 5. ES morphing ------------------------------------------------------
    # Goal: turn the signal templates, which exist only for a grid of ES shifts
    # (the CH "masses" -8.0, -7.9, ..., 8.0 %, without 0.0), into ONE pdf that
    # depends continuously on the fit parameter ES_<cat>, so combine can fit the ES.
    #
    #   templates:   ES = -0.2      ES = -0.1      ES = +0.1          (one TH1 each)
    #                 _/\_           _/\_            _/\_
    #   morphed pdf at ES = 0.03:  shape AND yield interpolated between the two
    #                              neighbouring templates (-0.1 and +0.1)
    #
    # ch::CMSHistFuncFactory (CombinePdfs/src/CMSHistFuncFactory.cc) does, per
    # (bin, process):
    #   * nominal: builds a CMSHistFunc "<bin>_<proc>_morph" from the templates in
    #     EVENTS (ClonedScaledShape), so the yield vs ES is carried by the
    #     histograms themselves.  "Horizontal" morphing in ES_<cat> uses
    #     HorizontalType::Integral: it interpolates between the cumulative
    #     distributions of the two neighbouring ES templates, so a peak moves
    #     smoothly instead of two peaks being faded into each other.
    #     Bin errors of the signal templates are set to 0 -> no autoMCStats for it.
    #   * shape systematics: "vertical" morphs.  Their up/down templates (per ES
    #     point, rescaled to the nominal integral = pure shape effect) are
    #     interpolated in the nuisance parameter as usual; their normalisation
    #     effect (value_u/value_d = kappa) is interpolated LINEARLY in ES with a
    #     RooSpline1D and applied with AsymPow in "<bin>_<proc>_morph_norm".
    #   * processes with only one "mass" (all backgrounds) get the same CMSHistFunc,
    #     just without horizontal morphing.
    #   * afterwards the CH entries are reduced to one per process with mass "*",
    #     rate 1 and no TH1: the yield now comes from the workspace objects
    #     (text2workspace picks up "<pdf>_norm" automatically), the data becomes
    #     the RooDataHist "<bin>_data_obs".
    # The tau ID SF is then the signal strength r (the signal normalisation) and
    # the ES is ES_<cat>; both are fitted together.
    #
    # The start value is tes_precision rather than 0.0 because 0.0 is not a grid point.
    es_var = ROOT.RooRealVar("ES_" + category, "ES_" + category, tes_precision, es_min, es_max)
    ws = ROOT.RooWorkspace("htt", "htt")
    getattr(ws, "import")(es_var)  # "import" is a python keyword
    morph_vars = cppyy.gbl.std.map["std::string", "RooAbsReal*"]()
    morph_vars[signal] = es_var  # only the signal is morphed in ES
    norm_postfix = cppyy.gbl.std.map["std::string", "std::string"]()
    norm_postfix[signal] = "norm"  # -> "<bin>_<signal>_morph_norm", the name text2workspace expects
    factory = cppyy.gbl.ch.CMSHistFuncFactory()
    factory.SetHorizontalMorphingVariable(morph_vars)
    factory.Run(cb, ws, norm_postfix)  # builds the pdfs/norms in ws and strips the TH1s from cb
    cb.AddWorkspace(ws)
    cb.ExtractPdfs(cb, "htt", "$BIN_$PROCESS_morph", "")  # attach the workspace pdfs to the CH processes
    cb.ExtractData("htt", "$BIN_data_obs")  # and the RooDataHist to the observations
    ws._es_var = es_var  # keep the python object alive

    # --- 6. datacards ---------------------------------------------------------
    # <output_dir>/<output_folder>/{cmb, mt, htt_mt_<cat>}/$BIN.txt + one ROOT file each.
    if write:
        out = os.path.join(output_dir, output_folder)
        writer = ch.CardWriter(os.path.join(out, "$TAG", "$BIN.txt"),
                               os.path.join(out, "$TAG", f"htt_input_{era_tag}{category}.root"))
        # We're not using mass as an identifier - which we need to tell the CardWriter otherwise it will see "*" as the mass value for every object and skip it
        writer.SetWildcardMasses([])  # ES shifts are not separate cards
        if verbose:
            writer.SetVerbosity(3)
        writer.WriteCards("cmb", cb)
        writer.WriteCards("mt", cb.cp().channel(channels))
        writer.WriteCards("htt_mt_" + category, cb.cp().channel(channels).bin_id([bin_id, 100]))

        # cb.PrintAll() writes to C++ std::cout: redirect it into a log file.
        logfile = ROOT.std.ofstream(os.path.join(out, "cb_PrintAll.log"))
        original = ROOT.std.cout.rdbuf()
        ROOT.std.cout.rdbuf(logfile.rdbuf())
        try:
            cb.PrintAll()
            ROOT.std.cout.flush()
        finally:
            ROOT.std.cout.rdbuf(original)
            logfile.close()

    print("[INFO] Done producing datacards.")
    return cb, ws
