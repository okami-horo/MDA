package membership

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func resetMembershipTestGlobals(t *testing.T) {
	t.Helper()

	oldAppVersion := appVersion
	oldClientName := clientName
	oldGenerateDeviceCodeV7 := generateDeviceCodeV7
	oldFetchMemberStatusFn := fetchMemberStatusFn

	t.Cleanup(func() {
		appVersion = oldAppVersion
		clientName = oldClientName
		generateDeviceCodeV7 = oldGenerateDeviceCodeV7
		fetchMemberStatusFn = oldFetchMemberStatusFn

		cachedStatusMu.Lock()
		cachedStatus = nil
		cachedStatusTime = time.Time{}
		cachedStatusMu.Unlock()

		deviceCodeMu.Lock()
		cachedDeviceCode = DeviceCodeV7{}
		deviceCodeCached = false
		deviceCodeMu.Unlock()
	})

	cachedStatusMu.Lock()
	cachedStatus = nil
	cachedStatusTime = time.Time{}
	cachedStatusMu.Unlock()

	deviceCodeMu.Lock()
	cachedDeviceCode = DeviceCodeV7{}
	deviceCodeCached = false
	deviceCodeMu.Unlock()
}

func TestStatusFromResponseUsesNewQuotaFields(t *testing.T) {
	status := statusFromResponse(&MemberStatusResponse{
		TierCode:                    "orange_pro",
		TierName:                    "Orange Pro",
		DailyRuntimeMinutes:         180,
		RegularDailyRuntimeMinutes:  60,
		SpecialPeriodRuntimeMinutes: 300,
		PaidThroughOn:               "20260701",
		HasFutureRenewal:            true,
	}, DeviceCodeV7{})

	if status.PaidThroughOn != "20260701" {
		t.Fatalf("PaidThroughOn = %q, want 20260701", status.PaidThroughOn)
	}
	if !status.HasFutureRenewal {
		t.Fatalf("HasFutureRenewal = false, want true")
	}
	if status.RegularDailyRuntimeMinutes != 60 {
		t.Fatalf("RegularDailyRuntimeMinutes = %d, want 60", status.RegularDailyRuntimeMinutes)
	}
	if status.DailyRuntimeMinutes != 60 {
		t.Fatalf("DailyRuntimeMinutes = %d, want compatibility alias 60", status.DailyRuntimeMinutes)
	}
	if status.SpecialPeriodRuntimeMinutes != 300 {
		t.Fatalf("SpecialPeriodRuntimeMinutes = %d, want 300", status.SpecialPeriodRuntimeMinutes)
	}
}

func TestStatusFromResponseFallsBackToTierSpecialQuota(t *testing.T) {
	status := statusFromResponse(&MemberStatusResponse{
		TierCode:            "orange_plus",
		TierName:            "Orange Plus",
		DailyRuntimeMinutes: 30,
	}, DeviceCodeV7{})

	if status.RegularDailyRuntimeMinutes != 30 {
		t.Fatalf("RegularDailyRuntimeMinutes = %d, want 30", status.RegularDailyRuntimeMinutes)
	}
	if status.SpecialPeriodRuntimeMinutes != 120 {
		t.Fatalf("SpecialPeriodRuntimeMinutes = %d, want fallback 120", status.SpecialPeriodRuntimeMinutes)
	}
}

func TestCheckMembershipReturnsLocalUnlimitedStatusWithoutRemoteCalls(t *testing.T) {
	resetMembershipTestGlobals(t)
	appVersion = "1.0.0"
	clientName = "MFAWPF"

	var deviceCodeCalls atomic.Int32
	var fetchCalls atomic.Int32
	generateDeviceCodeV7 = func() DeviceCodeV7 {
		deviceCodeCalls.Add(1)
		return DeviceCodeV7{CPUHash: "cpu-hash"}
	}
	fetchMemberStatusFn = func(DeviceCodeV7) (*MemberStatusResponse, error) {
		fetchCalls.Add(1)
		return &MemberStatusResponse{}, nil
	}

	status := checkMembership()

	if status.TierCode != "local" {
		t.Fatalf("TierCode = %q, want local", status.TierCode)
	}
	if !status.UnlimitedRuntime {
		t.Fatal("UnlimitedRuntime = false, want true")
	}
	if !status.IsMember {
		t.Fatal("IsMember = false, want true")
	}
	if !status.AllFeaturesUnlocked {
		t.Fatal("AllFeaturesUnlocked = false, want true")
	}
	if got := deviceCodeCalls.Load(); got != 0 {
		t.Fatalf("device code generated %d times, want 0", got)
	}
	if got := fetchCalls.Load(); got != 0 {
		t.Fatalf("membership status fetched %d times, want 0", got)
	}
}

func TestConcurrentMembershipChecksStayLocalAndOffline(t *testing.T) {
	resetMembershipTestGlobals(t)
	appVersion = "1.0.0"
	clientName = "MFAWPF"

	var deviceCodeCalls atomic.Int32
	var fetchCalls atomic.Int32
	generateDeviceCodeV7 = func() DeviceCodeV7 {
		deviceCodeCalls.Add(1)
		return DeviceCodeV7{CPUHash: "cpu-hash"}
	}
	fetchMemberStatusFn = func(DeviceCodeV7) (*MemberStatusResponse, error) {
		fetchCalls.Add(1)
		return &MemberStatusResponse{}, nil
	}

	const callers = 8
	statuses := make(chan *MembershipStatus, callers)
	var wg sync.WaitGroup
	wg.Add(callers)
	for range callers {
		go func() {
			defer wg.Done()
			statuses <- GetMembershipStatus()
		}()
	}
	wg.Wait()
	close(statuses)

	for status := range statuses {
		if !status.UnlimitedRuntime || !status.IsMember || !status.AllFeaturesUnlocked {
			t.Fatalf("membership status is not local unlimited: %+v", status)
		}
	}
	if got := deviceCodeCalls.Load(); got != 0 {
		t.Fatalf("device code generated %d times, want 0", got)
	}
	if got := fetchCalls.Load(); got != 0 {
		t.Fatalf("membership status fetched %d times, want 0", got)
	}
}
