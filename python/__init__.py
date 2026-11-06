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
from math import sqrt

import cppyy
import ROOT

from CombineHarvester.CombineTools import ch

cppyy.load_reflection_info("libCombineHarvesterCombinePdfs")  # for CMSHistFuncFactory

ERA_TAGS = {"2016preVFP": "Run2016preVFP", "2016postVFP": "Run2016postVFP",
            "2017": "Run2017", "2018": "Run2018"}

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
MC_REAL_TAU = ["ZTT", "TTT", "TTL", "VVT", "VVL", "STT", "STL"]  # simulated genuine (or lepton) tau_h
LUMI = {"Run2016preVFP": 1.012, "Run2016postVFP": 1.012, "Run2017": 1.0082, "Run2018": 1.0084}
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

    if embedding:  # genuine taus come from the embedded sample, not from MC
    #     ["W", "QCD", "ZL", "ZJ", "TTT", "TTL", "TTJ", "STT", "STL", "STJ", "VVJ", "VVT", "VVL"]
    # if embedding:  # genuine taus are in the embedded sample, so remove them from the MC backgrounds
    #     mt_bkgs = [p for p in mt_bkgs if p not in ["TTT", "STT", "VVT"]]
        mc = ["TTL", "TTJ", "W", "ZJ", "ZL", "VVL", "VVJ", "STL", "STJ"]
    else:
        mc = ["ZTT", "TTT", "TTL", "TTJ", "W", "ZJ", "ZL", "VVT", "VVL", "VVJ", "STT", "STL", "STJ"]

    add(["mt", "mm"], mc, "lumi_13TeV_$ERA", "lnN", LUMI[era_tag])
    
    # Run2 Prefiring Unerctainty: https://twiki.cern.ch/twiki/bin/viewauth/CMS/L1PrefiringWeightRecipe
    if not run3 and era_tag != "Run2018":
        add(["mt"], mc, "CMS_prefiring", "shape", 1.0)

    # Muon trigger/ID/iso: separate for MC and embedding, 4% in mm (two muons).
    add(["mt"], mc, "CMS_eff_m_trigger_$ERA", "shape", 1.0)
    # TODO: For Run3 the muon trigger ID/ISO/trigger uncertainties are derived from the SF measurement itself and is not a fiexed 4% uncertainty.
    if run3:
        for name in ["id", "iso"]:
            add(["mt", "mm"], EMB_PROCESSES, f"CMS_eff_m_{name}_emb_$ERA", "shape", 1.0) #TODO
            add(["mt", "mm"], mc, f"CMS_eff_m_{name}_$ERA", "shape", 1.0)                #TODO
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_trigger_emb_$ERA", "shape", 1.0)
    else:
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_trigger_emb_$ERA", "lnN", 1.02)
        for name in ["id", "iso"]:
            add(["mt"], EMB_PROCESSES, f"CMS_eff_m_{name}_emb", "lnN", 1.02)
            add(["mm"], EMB_PROCESSES, f"CMS_eff_m_{name}_emb", "lnN", 1.04)
            add(["mt"], mc, "CMS_eff_m_" + name, "lnN", 1.02)
            add(["mm"], mc, "CMS_eff_m_" + name, "lnN", 1.04)

    # 3% in Tau ID SF with different anti-l fake WP
    # Tau ID and ES of simulation. The embedded signal's ID and ES are what we measure, so they get no nuisance here.
    for dm in ["dm0", "dm1", "dm10", "dm11"]:
        add(["mt"], MC_REAL_TAU, f"CMS_eff_t_{dm}_$ERA", "shape", 1.0)
        add(["mt"], MC_REAL_TAU, f"CMS_scale_t_{dm}_$ERA", "shape", 1.0)

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
        add(["mt", "mm"], EMB_PROCESSES, "CMS_eff_m_emb_selection_trigger_$ERA", "shape", 1.0) #TODO: Those come from the SF measurement itself
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
            cb.cp().channel([chn]).signals().ExtractShapes(
                path, "$BIN/$PROCESS_$MASS", "$BIN/$PROCESS_$MASS_$SYSTEMATIC")

    # --- 4. template treatment -----------------------------------------------
    # Empty processes/templates make combine fail: drop them (and their systematics).
    empty = set()
    cb.ForEachProc(lambda p: empty.add((p.bin(), p.process(), p.mass())) if not p.rate() > 0 else None)
    cb.FilterProcs(lambda p: (p.bin(), p.process(), p.mass()) in empty)
    cb.FilterSysts(lambda s: (s.bin(), s.process(), s.mass()) in empty
                   or (s.type() == "shape" and (s.shape_u().Integral() == 0 or s.shape_d().Integral() == 0)))

    if not real_data:
        # Asimov data = sum of all templates.  As in the C++, this includes ALL
        # ES-shifted signal templates, so it is far too large; for a proper Asimov
        # fit use real_data=True and combine's "-t -1".
        for b in cb.bin_set():
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
        if cppyy.gbl.ch.HasNegativeBins(p.shape()):
            h = p.ClonedShape()
            cppyy.gbl.ch.ZeroNegativeBins(h.get())
            p.set_shape(h, False)

    def zero_negative_syst(s):
        if "shape" in s.type() and (cppyy.gbl.ch.HasNegativeBins(s.shape_u())
                                    or cppyy.gbl.ch.HasNegativeBins(s.shape_d())):
            h_u, h_d = s.ClonedShapeU(), s.ClonedShapeD()
            cppyy.gbl.ch.ZeroNegativeBins(h_u.get())
            cppyy.gbl.ch.ZeroNegativeBins(h_d.get())
            set_syst_shapes(s, h_u, h_d)

    cb.ForEachProc(zero_negative)
    cb.ForEachSyst(zero_negative_syst)

    if auto_rebin:
        # Merge bins from the right until each has > 1 background event; always
        # keep the boundaries of unrolled categories (multiples of 1 - first edge).
        # (The C++ also had a "merge to the right" branch whose condition was always false.)
        for b in cb.bin_set():
            shape = cb.cp().bin([b]).backgrounds().GetShape()
            n = shape.GetNbinsX()
            offset = shape.GetBinLowEdge(1)
            edges, content = [shape.GetBinLowEdge(n + 1)], 0.0
            for i in range(n, 0, -1):
                low = shape.GetBinLowEdge(i)
                content += shape.GetBinContent(i)
                if abs((low - offset) % (1.0 - offset)) < 1e-4 or content > 1.0:
                    edges.insert(0, low)
                    content = 0.0
            cb.cp().bin([b]).VariableRebin(edges)
        # Blind bins that are still below 1 background event.
        for b in cb.bin_set():
            shape = cb.cp().bin([b]).backgrounds().GetShape()
            for i in [i for i in range(1, shape.GetNbinsX() + 1) if shape.GetBinContent(i) < 1.0]:
                print("[INFO] Blind bin {} in {}".format(i, b))

                def blind(obj, i=i):
                    h = obj.ClonedShape()
                    h.SetBinContent(i, 0.0)
                    h.SetBinError(i, 0.0)
                    obj.set_shape(h, False)

                def blind_syst(s, i=i):
                    if "shape" in s.type():
                        h_u, h_d = s.ClonedShapeU(), s.ClonedShapeD()
                        for h in (h_u, h_d):
                            h.SetBinContent(i, 0.0)
                            h.SetBinError(i, 0.0)
                        set_syst_shapes(s, h_u, h_d)

                cb.cp().bin([b]).ForEachProc(blind)
                cb.cp().bin([b]).ForEachObs(blind)
                cb.cp().bin([b]).ForEachSyst(blind_syst)

    if manual_rebin_for_yields:  # one bin: only the yields remain
        for b in cb.bin_set():
            cb.cp().bin([b]).VariableRebin([0.0, 1.0])

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
                print("[WARNING] {} has no bin errors, no binomial bbb".format(proc.process()))
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
                s.set_name("CMS_htt_{}_{}_{}_{}_binomial_bin_{}".format(
                    proc.channel(), proc.bin(), era_tag, proc.process(), j))
                s.set_shapes(h_u, h_d, h)  # also sets value_u/d = integral ratios
                cb.CreateParameterIfEmpty(s.name())
                cb.InsertSystematic(s)

    ch.SetStandardBinNames(cb, "$ANALYSIS_$CHANNEL_$BINID_$ERA")  # e.g. htt_mt_7_Run2018
    cb.SetAutoMCStats(cb, 10.0)

    # --- 5. ES morphing ------------------------------------------------------
    # CMSHistFuncFactory interpolates between the ES templates: pdf <bin>_<proc>_morph(ES_<cat>).
    es_var = ROOT.RooRealVar("ES_" + category, "ES_" + category, tes_precision, es_min, es_max)
    ws = ROOT.RooWorkspace("htt", "htt")
    getattr(ws, "import")(es_var)  # "import" is a python keyword
    morph_vars = cppyy.gbl.std.map["std::string", "RooAbsReal*"]()
    morph_vars[signal] = es_var
    norm_postfix = cppyy.gbl.std.map["std::string", "std::string"]()
    norm_postfix[signal] = "norm"
    factory = cppyy.gbl.ch.CMSHistFuncFactory()
    factory.SetHorizontalMorphingVariable(morph_vars)
    factory.Run(cb, ws, norm_postfix)
    cb.AddWorkspace(ws)
    cb.ExtractPdfs(cb, "htt", "$BIN_$PROCESS_morph", "")
    cb.ExtractData("htt", "$BIN_data_obs")
    ws._es_var = es_var  # keep the python object alive

    # --- 6. datacards ---------------------------------------------------------
    # <output_dir>/<output_folder>/{cmb, mt, htt_mt_<cat>}/$BIN.txt + one ROOT file each.
    if write:
        out = os.path.join(output_dir, output_folder)
        writer = ch.CardWriter(os.path.join(out, "$TAG", "$BIN.txt"),
                               os.path.join(out, "$TAG", "htt_input_{}{}.root".format(era_tag, category)))
        writer.SetWildcardMasses(ROOT.std.vector("std::string")())  # ES shifts are not separate cards
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
