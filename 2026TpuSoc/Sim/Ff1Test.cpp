#include "VTpuNice.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// NICE command host + bounded 256 KiB DMA test memory. This is a core test,
// not a substitute for E203 execution or the competition's shared-SRAM bus.
struct Simulation {
    VTpuNice Top;
    std::vector<int16_t> Memory = std::vector<int16_t>(256 * 1024 / 2);
    uint64_t Cycles = 0, ReadBytes = 0, WriteBytes = 0, WriteAcks = 0;
    uint32_t Random = 2026, Address = 0, Beats = 0, Beat = 0, AckDelay = 0;
    bool Transfer = false, Direction = false, InHold = false, Ack = false;
    std::array<uint32_t, 4> HeldData{};

    uint32_t NextRandom() {
        Random ^= Random << 13;
        Random ^= Random >> 17;
        Random ^= Random << 5;
        return Random;
    }

    void Tick() {
        Top.Clock = 0;
        Top.MemoryRequestReady = !Transfer && !Ack && (NextRandom() & 3) != 0;
        Top.MemoryWriteDataReady = Transfer && Direction && (NextRandom() & 3) != 0;
        if (Transfer && !Direction && !InHold && (NextRandom() & 3) != 0) {
            for (int Lane = 0; Lane < 4; ++Lane) {
                uint32_t Index = Address / 2 + Beat * 8 + Lane * 2;
                HeldData[Lane] = uint16_t(Memory.at(Index))
                              | (uint32_t(uint16_t(Memory.at(Index + 1))) << 16);
            }
            InHold = true;
        }
        Top.MemoryReadDataValid = InHold;
        Top.MemoryReadDataLast = Transfer && Beat + 1 == Beats;
        Top.MemoryReadDataError = 0;
        for (int Lane = 0; Lane < 4; ++Lane) Top.MemoryReadData[Lane] = HeldData[Lane];
        Top.MemoryWriteResponseValid = Ack && AckDelay == 0;
        Top.MemoryWriteResponseError = 0;
        Top.eval();
        bool Request = Top.MemoryRequestValid && Top.MemoryRequestReady;
        bool Receive = Top.MemoryReadDataValid && Top.MemoryReadDataReady;
        bool Send = Top.MemoryWriteDataValid && Top.MemoryWriteDataReady;
        bool Acknowledge = Top.MemoryWriteResponseValid && Top.MemoryWriteResponseReady;
        uint32_t NextAddress = Top.MemoryRequestAddress;
        uint32_t NextBeats = Top.MemoryRequestBeatCount;
        bool NextDirection = Top.MemoryRequestWriteEnable;
        if (Request && (NextBeats == 0 || NextAddress % 16
            || uint64_t(NextAddress) + NextBeats * 16 > Memory.size() * 2))
            throw std::runtime_error("invalid/beyond-capacity DMA request");
        if (Send) {
            if (bool(Top.MemoryWriteDataLast) != (Beat + 1 == Beats))
                throw std::runtime_error("write last mismatch");
            for (int Lane = 0; Lane < 4; ++Lane) {
                uint32_t Index = Address / 2 + Beat * 8 + Lane * 2;
                Memory.at(Index) = int16_t(Top.MemoryWriteData[Lane] & 65535);
                Memory.at(Index + 1) = int16_t(Top.MemoryWriteData[Lane] >> 16);
            }
            WriteBytes += 16;
        }
        if (Receive) ReadBytes += 16;
        Top.Clock = 1;
        Top.eval();
        ++Cycles;
        if (Ack && AckDelay) --AckDelay;
        if (Acknowledge) { Ack = false; ++WriteAcks; }
        if (Receive || Send) {
            InHold = false;
            if (++Beat == Beats) {
                Transfer = false;
                if (Direction) { Ack = true; AckDelay = 4 + NextRandom() % 23; }
            }
        }
        if (Request) {
            Transfer = true;
            Direction = NextDirection;
            Address = NextAddress;
            Beats = NextBeats;
            Beat = 0;
        }
        if (Cycles > 20000000) throw std::runtime_error("FF1 watchdog");
    }

    void Reset() {
        Top.NiceRequestValid = 0;
        Top.NiceResponseReady = 0;
        Top.ResetN = 0;
        for (int Index = 0; Index < 4; ++Index) Tick();
        Top.ResetN = 1;
        Tick();
    }

    uint32_t Request(unsigned Function, uint32_t Rs1, uint32_t Rs2) {
        Top.NiceRequestInstruction = (Function << 25) | 0x707b;
        Top.NiceRequestSource1Data = Rs1;
        Top.NiceRequestSource2Data = Rs2;
        Top.NiceRequestValid = 1;
        do {
            Top.Clock = 0;
            Top.eval();
            bool Accepted = Top.NiceRequestReady;
            Tick();
            if (Accepted) break;
        } while (true);
        Top.NiceRequestValid = 0;
        while (!Top.NiceResponseValid) Tick();
        uint32_t Result = Top.NiceResponseData;
        if (Top.NiceResponseError) throw std::runtime_error("NICE instruction rejected");
        // Hold every instruction response for two clocks before consuming it.
        for (int Index = 0; Index < 2; ++Index) {
            Tick();
            if (!Top.NiceResponseValid || Top.NiceResponseData != Result || Top.NiceResponseError)
                throw std::runtime_error("NICE response changed under backpressure");
        }
        Top.NiceResponseReady = 1;
        Tick();
        Top.NiceResponseReady = 0;
        return Result;
    }

    void Wait(unsigned Mask) {
        uint32_t Status;
        do {
            Status = Request(3, 0, 0);
            if (Status & 0x30) throw std::runtime_error("TPU command/DMA error");
        } while (Status & Mask);
    }
};

static std::vector<int16_t> Read(const std::string& Name, size_t Count) {
    std::ifstream File(Name, std::ios::binary | std::ios::ate);
    if (!File || File.tellg() != std::streamoff(Count * 2))
        throw std::runtime_error("bad vector: " + Name);
    std::vector<int16_t> Values(Count);
    File.seekg(0);
    File.read(reinterpret_cast<char*>(Values.data()), Count * 2);
    return Values;
}

int main(int Argc, char** Argv) {
    Verilated::commandArgs(Argc, Argv);
    try {
        if (Argc != 2) throw std::runtime_error("usage: Ff1Test Cases.txt");
        std::ifstream Cases(Argv[1]);
        if (!Cases) throw std::runtime_error("cannot open FF1 cases");
        Simulation Sim;
        Sim.Reset();
        std::string InputPath, ParamsPath, ExpectedPath, Name;
        uint32_t Fraction;
        unsigned Count = 0;
        while (Cases >> InputPath >> ParamsPath >> ExpectedPath >> Fraction >> Name) {
            auto Input = Read(InputPath, 6336);
            auto Params = Read(ParamsPath, 16640);
            auto Expected = Read(ExpectedPath, 25344);
            constexpr uint32_t InputAddress = 0x1000, ParamsAddress = 0x15000, OutputAddress = 0x5000;
            std::copy(Input.begin(), Input.end(), Sim.Memory.begin() + InputAddress / 2);
            std::copy(Params.begin(), Params.end(), Sim.Memory.begin() + ParamsAddress / 2);
            std::fill(Sim.Memory.begin() + OutputAddress / 2 - 8,
                      Sim.Memory.begin() + OutputAddress / 2 + 25344 + 8, int16_t(0x5a5a));
            auto Start = Sim.Cycles, Reads = Sim.ReadBytes, Writes = Sim.WriteBytes, Acks = Sim.WriteAcks;
            Sim.Request(3, 0x3c, 0);
            Sim.Request(0, InputAddress, 0);
            Sim.Wait(2);
            Sim.Request(0, ParamsAddress, 3 | (6 << 4));
            Sim.Wait(2);
            for (uint32_t Row = 0; Row < 99; ++Row) {
                Sim.Request(1, 10 | (6 << 7) | (1 << 13) | (1 << 16) | (Fraction << 17), Row);
                Sim.Wait(1);
                Sim.Request(2, OutputAddress + Row * 512, 9 | (1 << 4));
                Sim.Wait(2);
                if (Sim.WriteAcks != Acks + Row + 1)
                    throw std::runtime_error("row completed before final write response");
            }
            for (size_t Index = 0; Index < Expected.size(); ++Index) {
                if (Sim.Memory.at(OutputAddress / 2 + Index) != Expected[Index]) {
                    std::ostringstream Error;
                    Error << Name << " [" << Index / 256 << ',' << Index % 256 << "] actual="
                          << Sim.Memory.at(OutputAddress / 2 + Index) << " expected=" << Expected[Index];
                    throw std::runtime_error(Error.str());
                }
            }
            for (int Index = 0; Index < 8; ++Index)
                if (Sim.Memory.at(OutputAddress / 2 - 8 + Index) != int16_t(0x5a5a)
                    || Sim.Memory.at(OutputAddress / 2 + 25344 + Index) != int16_t(0x5a5a))
                    throw std::runtime_error("FF1 output boundary overwritten");
            if (Sim.ReadBytes - Reads != 45952 || Sim.WriteBytes - Writes != 50688)
                throw std::runtime_error("unexpected FF1 DMA traffic");
            std::cout << "PASS FF1 " << Name << ": 25344 bit-exact values, 99 acknowledged rows, "
                      << Sim.Cycles - Start << " cycles (NICE host, randomized DMA stalls)" << std::endl;
            ++Count;
        }
        if (!Cases.eof() || Count != 15) throw std::runtime_error("incomplete FF1 cases");
        std::cout << "PASS FF1: 15 cases, compact 112 KiB private SRAM, no reset between cases" << std::endl;
        return 0;
    } catch (const std::exception& Error) {
        std::cerr << "FAIL FF1: " << Error.what() << std::endl;
        return 1;
    }
}
